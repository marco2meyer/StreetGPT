## ADDED Requirements

### Requirement: Pacing target of ~9 turns / ~9 minutes

Each of the three protocols (`no_claim`, `with_claim`, `with_claim_control`) SHALL state a pacing target of approximately 9 turns and approximately 9 minutes for the full conversation. The prompt SHALL NOT instruct the bot to "perform AT LEAST 3 method-quality probes" or any equivalent that forces the conversation past the 9-turn target.

#### Scenario: Treatment prompt declares the new target
- **WHEN** an operator reads the PACING & DURATION block of `no_claim` or `with_claim`
- **THEN** the target stated is approximately 9 turns / 9 minutes, not 12 turns / 8 minutes

#### Scenario: Probe count requirement is removed
- **WHEN** an operator reads the prompt body
- **THEN** there is no instruction requiring at least three distinct method-quality probes before the summary

### Requirement: Opening turn does not ask for a nickname

All three protocols SHALL open with a brief greeting and the first substantive step (anchoring the claim or asking the participant what's on their mind). The protocols SHALL NOT ask "What nickname should I use for you here?" or any equivalent. Subsequent turns SHALL address the participant as "you".

#### Scenario: Opening section contains no nickname prompt
- **WHEN** an operator reads section 1 (OPEN) of any of the three protocols
- **THEN** the section contains no question asking for a nickname

#### Scenario: Prompt body uses second-person address
- **WHEN** an operator reads the prompt body
- **THEN** participant references use "you" / "your", not a nickname placeholder or instruction to insert one

### Requirement: Treatment probe sequence is strongest-reason then reservations/alternatives then adjudication

The `no_claim` and `with_claim` protocols SHALL structure the substantive middle of the conversation as three ordered steps: (a) elicit the participant's strongest single reason for the belief, (b) elicit reservations and, in the same step, offer competing non-conspiratorial explanations, (c) ask an adjudication question about how someone could decide between the conspiratorial reading and the alternatives. The prompt SHALL NOT list more probe categories than are needed for these three steps.

#### Scenario: Probe section names the three steps
- **WHEN** an operator reads the METHOD / QUALITY PROBES section of `no_claim` or `with_claim`
- **THEN** it presents exactly the three ordered steps above, in that order

#### Scenario: Granular operationalization probes are removed
- **WHEN** an operator reads the probe section
- **THEN** it does NOT contain "what would a good test look like in practice", "what concrete dataset would show…", or other expert-coded operationalization prompts

### Requirement: Treatment protocols MUST offer alternative explanations in at least one turn

The `no_claim` and `with_claim` protocols SHALL instruct the bot that, in at least one turn during the substantive middle of the conversation, it MUST offer two or more non-conspiratorial explanations that could account for the same observation. The prompt SHALL require these alternatives be framed as candidates for the participant to evaluate against, and SHALL forbid framing them as endorsed positions, mainstream consensus, or "what really happened". Immediately after offering alternatives, the bot SHALL ask the participant how someone could decide between the conspiratorial reading and the alternatives.

#### Scenario: Prompt mandates the alternatives turn
- **WHEN** an operator reads the probe section of `no_claim` or `with_claim`
- **THEN** there is an explicit instruction that the bot MUST offer at least two alternative explanations in at least one turn

#### Scenario: Framing constraint is explicit
- **WHEN** an operator reads the alternatives instruction
- **THEN** the instruction explicitly forbids presenting alternatives as endorsed positions or mainstream narrative

#### Scenario: Adjudication question follows alternatives
- **WHEN** an operator reads the alternatives instruction
- **THEN** the instruction requires asking the participant how someone could decide between the conspiratorial reading and the alternatives, in the same or next turn

### Requirement: Control protocol uses the consolidated category set

The `with_claim_control` protocol SHALL use exactly these neutral-prompt categories, and no others: a single combined "Meaning / personal salience" category, "First encounter / history", "Examples / imagery", and "Change over time". The "Communication" category (asking what the participant would want someone to get right), the "Social meaning" category (asking whether others mean the same thing), and the separate "Personal salience" category SHALL be removed. The prompt SHALL require at least three prompts drawn from different remaining categories, with at most one short follow-up per category.

#### Scenario: Removed categories are absent
- **WHEN** an operator reads the SAME-CLAIM NEUTRAL CONVERSATION section
- **THEN** there is no "Communication" category and no "Social meaning" category

#### Scenario: Meaning and Personal are merged
- **WHEN** an operator reads the category list
- **THEN** "Meaning / wording" and "Personal salience" appear as a single combined category, not as two separate entries

### Requirement: Endline re-check re-states the clarified discussion claim verbatim

In all three protocols, the RE-CHECK CONFIDENCE step SHALL instruct the bot to quote the participant's clarified discussion claim verbatim (as confirmed earlier in the conversation) immediately before asking for the final 0–10 rating, so the participant is not re-rating from memory. The 0–10 scale anchors used at endline SHALL match those used at baseline (0 = strongly disagree, 5 = neither agree nor disagree, 10 = strongly agree).

#### Scenario: Endline instruction names verbatim restatement
- **WHEN** an operator reads the RE-CHECK CONFIDENCE step in any of the three protocols
- **THEN** the instruction explicitly tells the bot to quote the clarified discussion claim verbatim before asking for the final rating

#### Scenario: Endline scale matches baseline
- **WHEN** an operator compares the CONFIDENCE (NUMERIC) baseline step and the RE-CHECK CONFIDENCE endline step in `with_claim` and `with_claim_control`
- **THEN** both use the 0–10 anchors (0 = strongly disagree, 5 = neither agree nor disagree, 10 = strongly agree)

### Requirement: `control_claim` placeholder is removed from prompts and code paths

The `with_claim_control` prompt SHALL NOT reference `{control_claim}`. The application code path that builds the chat-outcome extraction call SHALL NOT accept or pass a `control_claim` argument.

#### Scenario: Placeholder absent from prompt
- **WHEN** an operator searches `config/system_messages.yaml` for `{control_claim}`
- **THEN** there are no matches

#### Scenario: Extraction call does not take control_claim
- **WHEN** an operator reads the `build_chat_outcome` function signature and body in `streamlit_app.py`
- **THEN** there is no `control_claim` parameter and no use of it in the extraction user message
