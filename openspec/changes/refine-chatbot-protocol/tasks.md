## 1. Rewrite the `no_claim` protocol

- [x] 1.1 Remove the "What nickname should I use for you here?" question from section 1 (OPEN); replace with a brief greeting and the first substantive question.
- [x] 1.2 Update PACING & DURATION to target ~9 turns / ~9 minutes; remove the "AT LEAST 3 method-quality probes" instruction.
- [x] 1.3 Replace the METHOD / QUALITY PROBES menu with the three ordered steps: (a) strongest single reason, (b) reservations + offer two-or-more non-conspiratorial alternative explanations (framed as candidates, not endorsed positions), (c) adjudication question ("how could someone decide between the conspiratorial reading and these alternatives?").
- [x] 1.4 Remove granular expert-coded probes (e.g., "what would a good test look like in practice", "what concrete dataset would show…") from the prompt body.
- [x] 1.5 Remove second-person nickname references; verify the prompt uses "you" / "your" throughout.
- [x] 1.6 In the RE-CHECK CONFIDENCE step, instruct the bot to quote the clarified discussion claim verbatim immediately before asking for the final 0–10 rating.

## 2. Rewrite the `with_claim` protocol

- [x] 2.1 Remove the nickname question from section 1.
- [x] 2.2 Update PACING & DURATION as in 1.2.
- [x] 2.3 Replace the METHOD / QUALITY PROBES menu as in 1.3, with the explicit framing constraint that alternatives must be presented as candidates and never as endorsed positions or mainstream narrative.
- [x] 2.4 Remove granular expert-coded probes from the prompt body as in 1.4.
- [x] 2.5 In the RE-CHECK CONFIDENCE step, instruct the bot to quote `{survey_claim}` clarification (the participant's clarified discussion claim) verbatim before the final 0–10 rating; confirm baseline and endline both use 0–10 with anchors 0 = strongly disagree, 5 = neither agree nor disagree, 10 = strongly agree.
- [x] 2.6 Remove "What nickname should I use for you here?" or equivalent from anywhere in the body.

## 3. Rewrite the `with_claim_control` protocol

- [x] 3.1 Remove the nickname question from section 1.
- [x] 3.2 Update PACING & DURATION to target ~9 turns / ~9 minutes.
- [x] 3.3 In the SAME-CLAIM NEUTRAL CONVERSATION section, remove the "Communication" category ("what would you want someone to get right…") and the "Social meaning" category ("do others mean the same as you…").
- [x] 3.4 Merge "Meaning / wording" and "Personal salience" into a single combined category in the same section.
- [x] 3.5 Confirm there are no remaining `{control_claim}` references anywhere in the prompt block.
- [x] 3.6 In the RE-CHECK CONFIDENCE step, instruct the bot to quote the clarified discussion claim verbatim before the final 0–10 rating, with the same anchors as baseline.

## 4. Remove the `control_claim` plumbing from the app

- [x] 4.1 In `streamlit_app.py`, drop `control_claim` from the `build_chat_outcome` function signature, its docstring/explanatory strings if any, and the extraction user-message body.
- [x] 4.2 Remove the call-site argument passing `control_claim` into `build_chat_outcome`.
- [x] 4.3 Grep the repo for any remaining `control_claim` references and remove dead ones (or document why a remaining one is intentional). — Removed from `scripts/setup_prolific_qualtrics.py`. Remaining matches are inside deployed `.qsf` Qualtrics survey definitions; the app ignores unknown URL params, so leaving them in the live survey is harmless and avoids re-uploading Qualtrics state.

## 5. Add chat-duration tracking

- [x] 5.1 Add a helper that returns the current UTC time as an ISO 8601 string (use existing `pytz` import if appropriate, otherwise `datetime.now(timezone.utc).isoformat()`).
- [x] 5.2 In the user-message handler, before persisting the turn, set `chat_started_at` on the session document via `$setOnInsert`-style guard (or an `if not already set` check in the existing `update_one`) so it is written exactly once on the first user message.
- [x] 5.3 At the point where `input_active` transitions to 0 (chat-end path), compute `chat_ended_at` and `chat_duration_seconds = round((end - start).total_seconds())` and include them in the Mongo upsert for that turn, guarded so subsequent re-runs do not rewrite them.
- [x] 5.4 Verify abandoned sessions (no end reached) leave `chat_ended_at` and `chat_duration_seconds` unset. — Confirmed: end fields are only added to the Mongo `$set` payload when `st.session_state["chat_ended_at"]` is truthy, which only happens inside the `should_end_chat` branch; abandoned sessions never enter that branch.

## 6. Smoke-test end-to-end

- [ ] 6.1 Run the app locally (`streamlit run streamlit_app.py`) and walk one treatment session and one control session through to the goodbye turn.
- [ ] 6.2 Confirm the resulting MongoDB document has `chat_started_at`, `chat_ended_at`, and `chat_duration_seconds` populated, and that `chat_duration_seconds` is a plausible integer.
- [ ] 6.3 Confirm the conversations stay close to ~9 turns and that the alternative-explanations + adjudication turn occurs in both treatment conversations.
- [ ] 6.4 Confirm the endline re-check quotes the clarified discussion claim verbatim.

## 7. Deploy

- [ ] 7.1 Commit changes on `main`.
- [ ] 7.2 Rebuild the `app` container on the Hetzner host (`docker compose up -d --build app`).
- [ ] 7.3 Run one production smoke session through Prolific preview mode and confirm Mongo writes look correct.
