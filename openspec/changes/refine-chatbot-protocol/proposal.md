## Why

Pilot sessions of the Street Epistemology chatbot currently take 12–13 minutes at minimum, exceeding our Prolific time budget of 9–10 minutes and risking participant fatigue. Several prompts also overshoot a survey-participant audience: they read as expert-level evidence-quality probes, ask the participant to summarize rather than examine their own belief, or duplicate one another. The most generative move observed in pilots — offering competing non-conspiratorial explanations and asking the participant how to decide between them — happens inconsistently. We also have no server-side measurement of how long each chat actually takes, so we cannot verify the time reduction or analyze duration alongside credence shifts.

## What Changes

- Shorten both `no_claim` and `with_claim` protocols to a target of ~9 minutes / ~9 turns, down from the current ~12 minutes / ~12 turns. Cut "biggest contributor + 3 distinct probes + follow-ups + summary + re-check" to "strongest reason → reservations / alternative explanations → adjudication question → summary + re-check".
- Remove the opening nickname prompt from all three protocols (`no_claim`, `with_claim`, `with_claim_control`). Address the participant as "you".
- Replace the current "method/quality probes" menu with a tighter, plain-language probe set built around: (a) strongest reason for the belief, (b) reservations and alternative explanations, (c) an adjudication probe ("how could someone decide between the conspiratorial reading and a non-conspiratorial one?").
- Promote "alternative explanations" from one technique among many to a consistently-offered move. The bot must explicitly frame alternatives as candidates to evaluate against, not as endorsed positions or mainstream narratives.
- Cut overly granular, expert-coded probes (e.g., "what concrete dataset would show…", "what would a good test look like in practice"). Keep operationalization implicit, not as a question.
- In the control protocol, remove the confusing or redundant prompt categories: "Communication" ("what would you want someone to get right"), "Social meaning" ("do others mean the same"), and collapse "Meaning / wording" and "Personal salience" into a single category since participants experienced them as repetitive.
- At the endline re-check, the bot must re-state the participant's clarified discussion claim verbatim before asking for the final 0–10 rating, so participants are not re-rating from memory after 8+ turns.
- **BREAKING**: Drop the now-unused `control_claim` parameter from prompt rendering and the chat-outcome extraction call site. Already removed from the control prompt body in the previous commit; this change removes the remaining plumbing.
- Track per-session interaction duration in MongoDB: record `chat_started_at` on first user message, `chat_ended_at` when the goodbye is emitted, and a derived `chat_duration_seconds` on the persisted record.

## Capabilities

### New Capabilities
- `conversation-protocol`: The chatbot's structured conversation flow (sections, ordering, probe categories, pacing targets, opening, claim anchoring, endline re-check) for the `no_claim`, `with_claim`, and `with_claim_control` modes.
- `chat-duration-tracking`: Server-side recording of when each chat session starts and ends so duration can be analyzed alongside other per-session fields in MongoDB.

### Modified Capabilities
<!-- None: no existing specs in openspec/specs/ — this is the first OpenSpec change in the repo. -->

## Impact

- `config/system_messages.yaml` — rewrite all three protocol blocks (`no_claim`, `with_claim`, `with_claim_control`); remove nickname step; replace probe menu; add verbatim claim re-statement at endline; drop `{control_claim}` placeholder.
- `streamlit_app.py` — drop the `control_claim` argument from the `build_chat_outcome` call site and its prompt; persist `chat_started_at`, `chat_ended_at`, and `chat_duration_seconds` on the Mongo document; populate `chat_started_at` on first user message and finalize on chat end.
- MongoDB schema (no migration tool — additive fields, written by the app) — new fields on per-session documents in the existing collection.
- Preregistration doc `OSF_preregistration_election_conspiracy_experiment.md` — note the protocol revision (separately; not modified by code, but flagged for the user to update before recruitment).
- No external API or dependency changes.
