## Context

The chatbot is implemented as a Streamlit app (`streamlit_app.py`) that loads three prompt blocks from `config/system_messages.yaml` (`no_claim`, `with_claim`, `with_claim_control`) and sends them to OpenAI as the system message for each turn. The structure and pacing of the conversation are governed almost entirely by these YAML prompts, not by app code. The app does, however, control:

- when chat input is enabled or disabled (`input_active` flag),
- when an extraction LLM call is fired to pull `discussion_claim` / credences from the transcript (`build_chat_outcome`),
- what gets persisted to MongoDB (per-session document with conversation, claim, credences, and metadata).

We have a fresh production deploy on Hetzner behind Caddy with a working Prolific/Qualtrics handoff. The control protocol was just refactored to stay on the participant's clarified discussion claim (no more `{control_claim}` switch), and the chat-return handoff was switched to a base64 payload via `/return-bridge.html`. The current pilot timings (12–13 min) come from running the full ~12-turn protocol with multi-probe + follow-up loops.

## Goals / Non-Goals

**Goals:**
- Reduce target chat length to ~9 turns / ~9 minutes for both treatment protocols.
- Make the protocol behaviorally simpler: strongest-reason → reservations / alternatives → adjudication.
- Make "offer alternative explanations and ask how to decide between them" a consistent, mandatory move in the treatment protocols rather than one technique among many.
- Eliminate confusing or redundant control-mode prompts.
- Always show the participant's clarified discussion claim verbatim at endline re-check.
- Record per-session duration in MongoDB so we can analyze it and verify the time reduction.

**Non-Goals:**
- Changing the OpenAI model, retry policy, or token-budgeting code.
- Changing the Qualtrics survey, the Prolific routing, or the return-bridge mechanism.
- Migrating historical MongoDB documents to backfill duration fields.
- Adding analytics dashboards or visualization for duration data.
- Changing the preregistration document (the user will revise that separately before recruitment).

## Decisions

### Decision 1: Keep protocol changes inside YAML, not code

All conversation-flow changes (shorter sequence, removed nickname step, new probe set, mandatory-alternatives instruction, verbatim endline re-statement) are made by editing `config/system_messages.yaml`. Rationale: the prompts already govern flow; making a new "protocol state machine" in Python would duplicate work the LLM is already doing well and would be brittle. Alternative considered: scripting a fixed turn-by-turn flow in Python with the LLM only generating wording. Rejected as overkill for the time-to-recruitment we have, and because it would constrain the bot's responsiveness to participant phrasing.

### Decision 2: Mandatory-alternatives instruction is phrased as a rule with a framing requirement

The prompt will instruct the bot: "You MUST, in at least one turn during the middle of the conversation, offer two or more non-conspiratorial explanations that could account for the same observation, framed as candidates to evaluate against — never as endorsed positions or as the 'mainstream view'. Then ask the participant how someone could decide between the conspiratorial reading and these alternatives." Rationale: matches the move the user found most generative in pilot. Alternative considered: leaving alternatives as one of N optional techniques. Rejected because the user's review showed it happened inconsistently and was the most valuable move when it did.

### Decision 3: Endline re-statement uses a placeholder, not transcript-paraphrase

At the endline re-check turn, the prompt will instruct the bot to quote the clarified discussion claim verbatim before asking for the final 0–10 rating. Because the discussion claim is established by the bot itself earlier in the conversation (and we don't pass it back into the system prompt mid-conversation), the bot must remember its own confirmation from earlier turns. We rely on the LLM's context window for this rather than threading the value through state. Rationale: simplest path; the conversation is short enough (≤9 turns) that the model reliably retains its own claim confirmation. Alternative considered: extracting the clarified claim mid-conversation and injecting it into the system message as `{discussion_claim}` for the endline turn. Rejected as significantly more complex (requires mid-stream extraction + system-message rewrite); we can fall back to it if pilots show the bot fails to re-state accurately.

### Decision 4: Duration tracking is additive, written by the app on existing persistence boundaries

Add three fields to the per-session MongoDB document:
- `chat_started_at` (UTC ISO 8601 string): set the first time a user message is appended in this session.
- `chat_ended_at` (UTC ISO 8601 string): set when `input_active` transitions to 0 (chat end).
- `chat_duration_seconds` (number): computed as `chat_ended_at - chat_started_at`.

These are written inside the existing `update_one` upsert that runs after each turn. Rationale: zero new persistence machinery, idempotent (set-on-first-set semantics via `$setOnInsert` for `chat_started_at` and a guarded `$set` for the end fields). Alternative considered: a separate `chat_timings` collection. Rejected because we already have one document per session and want duration alongside the conversation for analysis.

### Decision 5: Drop the `control_claim` parameter from `build_chat_outcome`

The control-prompt body no longer uses `{control_claim}` (removed in the previous commit). The app still passes `control_claim` into the extraction-call user message. Remove this argument. Rationale: dead parameter. Alternative considered: leave it for backwards compatibility. Rejected because no historical caller depends on it and the project guidance prefers removing unused code over keeping shims.

## Risks / Trade-offs

- **[Risk] Shortening to 9 turns under-probes some participants** → Mitigation: keep the "if a new major reason is introduced, loop back" instruction so the bot can extend when warranted. Treat 9 turns as a target, not a hard cap.
- **[Risk] LLM forgets the clarified discussion claim and paraphrases it inaccurately at endline** → Mitigation: keep this assumption under observation in the next pilot batch; if accuracy is poor, escalate to Decision 3's rejected alternative (mid-stream extraction + system-message injection).
- **[Risk] "Mandatory alternatives" turn comes across as the bot pushing a mainstream view** → Mitigation: the prompt explicitly frames alternatives as candidates to evaluate against, requires more than one, and ties the move to an adjudication question the participant answers — not a conclusion the bot draws.
- **[Risk] Duration field gets set but participant abandons before chat end** → Mitigation: `chat_started_at` is still recorded; `chat_ended_at` and `chat_duration_seconds` simply remain unset on abandoned sessions, which is the correct semantics for filtering analyses to completed chats.
- **[Trade-off] No historical backfill of duration** → Pre-existing pilot data won't have duration fields. Acceptable: analyses requiring duration will be from the confirmatory run only, consistent with the preregistration's "post-preregistration timestamp" rule.

## Migration Plan

1. Edit `config/system_messages.yaml` for all three protocols.
2. Edit `streamlit_app.py`: drop `control_claim` from the extraction call site; add the three duration fields to the per-turn Mongo upsert.
3. Deploy: rebuild the `app` container (`docker compose up -d --build app`) on the Hetzner host. The Caddy and Mongo containers are unaffected.
4. Smoke test: run one end-to-end chat through both treatment and control modes and confirm the persisted Mongo document has the three duration fields populated.
5. Rollback: revert the commit and rebuild. No schema migration to undo (additive fields are tolerated by reads).

## Open Questions

- Should we add a hard time cap (e.g., the bot auto-closes after 12 minutes)? Currently no — the user asked for a shorter target, not a kill switch. Revisit if pilots show drift.
- Should `chat_duration_seconds` be computed at write time or derived at read time from the two timestamps? Compute at write time for ergonomic querying; cheap and unambiguous.
