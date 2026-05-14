# OSF-Style Preregistration Draft: Clarification and Confidence Change for Selected Conspiracy-Themed Survey Items

## Status note

This draft is intended for the main confirmatory study, not for previously collected pilot, preview, or debugging data. Only responses collected after the preregistration timestamp, using the finalized versions of the Qualtrics survey and chatbot protocol archived with this registration, will count as confirmatory data. Earlier pilot data may be used only for software validation, feasibility checks, and exploratory analyses that are clearly labeled as such.

Administrative fields to complete before OSF submission:

- Preregistration date: `[INSERT DATE]`
- Planned recruitment start date: `[INSERT DATE]`
- Planned stopping date (if any): `[INSERT DATE OR NONE]`
- Planned Prolific eligibility filters: `[INSERT FILTERS]`
- Planned compensation: `[INSERT AMOUNT]`
- Target number of completed Qualtrics responses: `[INSERT N]`
- Target number of completed chatbot cases: `[INSERT N]`

## Title

High agreement with these selected survey items may sometimes correspond to less explicitly conspiratorial reformulations of the same issue, and a same-claim reflective chatbot conversation may reduce self-reported confidence in a clarified discussion claim relative to a same-claim neutral control.

## Study overview

Participants first complete a Qualtrics survey that includes 10 conspiracy-themed target items rated on a 0-10 agree/disagree scale. Any participant who rates at least one target item at 6 or above is routed to a chatbot. One qualifying item is selected at random and passed into the chatbot as the participant's `survey_claim`, together with the participant's original rating (`survey_claim_initial_credence`).

At the start of the chatbot conversation, the participant is shown two possible interpretations of the selected claim. Interpretation A is the more explicitly conspiratorial reading. Interpretation B is a less conspiratorial reading that does not attribute the outcome to intentional covert coordination. The participant may accept A, accept B, or offer another reformulation in their own words. The chatbot then confirms the clarified discussion claim and asks for a 0-10 baseline confidence rating on that clarified claim (`discussion_claim_initial_credence`).

In the treatment condition, the middle part of the chatbot conversation stays on the participant's clarified discussion claim and uses Street Epistemology-style prompts about reasons, doubts, alternatives, testability, and related epistemic considerations. In the control condition, the conversation also stays on that same clarified discussion claim, but uses neutral, non-evaluative prompts about meaning, wording, personal salience, communication, examples, and first encounter rather than prompts about evidence quality, testability, or what would change the participant's mind. In both conditions, the chatbot ends by asking for a final 0-10 confidence rating on the clarified discussion claim (`discussion_claim_final_credence`).

After the chatbot, Qualtrics asks the participant to re-rate the original survey claim on the same 0-10 scale (`survey_claim_final_c`).

The active survey currently randomizes participants into one control slot and four treatment slots, yielding an intended allocation of 20% control and 80% treatment. The between-condition contrast is therefore interpretable as the effect of a same-claim reflective conversation relative to a same-claim neutral conversation with matched topic, baseline rating, endline rating, and overall conversational structure.

## Research questions

### RQ1

When participants rate one of these target survey items at 6 or higher, how do they clarify what they mean when the chatbot offers a more explicitly conspiratorial reading, a less explicitly conspiratorial reading, or space for their own reformulation?

### RQ2

Compared with a same-claim neutral chatbot conversation, does a same-claim reflective chatbot conversation produce lower endline confidence in the participant's clarified discussion claim?

## Confirmatory hypotheses

The confirmatory family contains two hypotheses: H1 and H2. To control the familywise error rate, their p-values will be adjusted using the Holm procedure. All remaining analyses, including the within-treatment pre/post comparison, are secondary or exploratory.

### H1: Clarification hypothesis

Among chatbot participants, clarified discussion claims coded as non-explicitly conspiratorial will be more common than clarified discussion claims coded as explicitly conspiratorial.

### H2: Between-condition protocol hypothesis

After adjusting for discussion baseline confidence, participants assigned to the same-claim reflective chatbot condition will show lower discussion endline confidence than participants assigned to the same-claim neutral chatbot control condition.

## Secondary outcomes

These outcomes are pre-specified but secondary. They will be reported clearly as secondary rather than primary confirmatory tests.

1. Clarification shift: discussion baseline minus survey baseline (`discussion_claim_initial_credence - survey_claim_initial_credence`).
2. Original-item post-chat change: survey endline minus survey baseline (`survey_claim_final_c - survey_claim_initial_credence`).
3. Combined shift from original survey item to clarified discussion endline (`discussion_claim_final_credence - survey_claim_initial_credence`).
4. Within-treatment discussion-claim change from discussion baseline to discussion endline.
5. Raw descriptive distribution of explicit A choices, explicit B choices, and participant-generated reformulations when the transcript makes that distinction directly observable.
6. Descriptive distribution of clarification responses across:
   - A-consistent
   - B-consistent
   - participant-generated other reformulation coded explicitly conspiratorial
   - participant-generated other reformulation coded non-explicitly conspiratorial
   - unclassifiable

No correction for multiple testing will be applied to these secondary outcomes because they are not primary confirmatory tests; they will be interpreted cautiously and labeled as secondary.

## Design

- Platform: Qualtrics survey plus external chatbot.
- Recruitment source: Prolific.
- Population: Prolific participants meeting the eligibility settings active at launch.
- Unit of analysis: participant.
- Scope of inference: all confirmatory claims are restricted to this specific set of 10 target items and to this survey-to-chatbot protocol.
- Randomization relevant to this preregistration:
  - One eligible conspiracy-themed item is selected at random from the participant's target items rated 6 or higher.
  - Participants are randomized before chatbot launch to a same-claim neutral control condition (20%) or a same-claim reflective treatment condition (80%) via the Qualtrics survey flow.
  - Both arms use the same selected survey claim, the same A/B clarification step, the same discussion baseline rating, and the same discussion endline rating. The arms differ only in the style of the middle conversational prompts.
- Blinding:
  - Participants are not blind to the fact that they are conversing with a chatbot.

## Sampling plan

### Inclusion into the survey

All consented respondents who complete the main study during the preregistered collection window will be included in the survey-level dataset, subject to the exclusion criteria below.

### Inclusion into the chatbot analyses

Participants enter the chatbot analyses only if:

1. They consent to the survey.
2. They are not a Qualtrics preview/test response.
3. They rate at least one target conspiracy-themed item at 6 or higher, causing a `survey_claim` to be selected.
4. A chatbot session is successfully launched and stored.

### Stopping rule

Data collection will stop when the first of the following occurs:

1. The study reaches `[INSERT TARGET NUMBER OF COMPLETED QUALTRICS RESPONSES]`.
2. The study reaches `[INSERT TARGET NUMBER OF COMPLETED CHATBOT CASES]`.
3. The preregistered stopping date is reached.

No optional stopping will be used beyond this preregistered rule.

Before OSF submission, this section should be supplemented with a power analysis or precision analysis tied to the final target N, expected chatbot-entry rate, expected attrition, and the current 20/80 arm allocation.

## Measures

### Target survey claims

The active Qualtrics survey uses the following 10 target items to determine chatbot entry and to define the original `survey_claim`:

1. Election fraud was widespread enough to influence the outcome of the 2020 Presidential Elections in favor of Joe Biden.
2. Democrats organize non-citizens (e.g., undocumented immigrants) to vote illegally in U.S. elections to rig elections.
3. Democrats commit widespread voter fraud in U.S. elections through manipulating mail-in voting and voting machines.
4. Elon Musk's company, SpaceX, used its Starlink satellite technology to manipulate election results during the 2024 U.S. presidential election.
5. Donald Trump's campaign team coordinated with the Russian government to interfere in the 2016 Presidential Election.
6. Republicans won the presidential elections in 2016, 2004, and 2000 by stealing them.
7. Jeffrey Epstein, the billionaire accused of running an elite sex trafficking ring, was murdered to cover up the activities of his criminal network.
8. There was a broad conspiracy, rather than a lone gunman, responsible for the assassination of President Kennedy.
9. The truth about the harmful effects of vaccines is being deliberately hidden from the public.
10. Regardless of who is officially in charge of governments and other organizations, there is a single group of people who secretly control events and rule the world together.

### Primary variables

- `survey_claim`: the randomly selected original target item.
- `survey_claim_initial_credence`: the participant's original 0-10 endorsement of that item in Qualtrics.
- `discussion_claim`: the clarified claim established in the chatbot after the A/B-or-other step.
- `discussion_claim_initial_credence`: the participant's 0-10 baseline confidence in the clarified discussion claim.
- `discussion_claim_final_credence`: the participant's 0-10 endline confidence in the clarified discussion claim.
- `survey_claim_final_c`: the participant's post-chat 0-10 rerating of the original survey claim in Qualtrics.
- `control_flag`: binary indicator for same-claim neutral control vs treatment condition.

### Clarification coding for H1

The primary H1 outcome is not a simple record of whether the participant typed the letter "A" or "B". Instead, it is based on the clarified discussion claim that the chatbot and participant settle on before the discussion baseline rating is taken. This is a claim-clarification outcome, not a direct measure of a participant's latent underlying belief independent of the conversation.

Each clarified claim will be coded into one of five mutually exclusive categories:

1. **A-consistent explicit conspiracy**: the participant endorses interpretation A or produces a reformulation substantively equivalent to A.
2. **B-consistent non-explicit claim**: the participant endorses interpretation B or produces a reformulation substantively equivalent to B.
3. **Other explicit conspiracy**: the participant offers a different reformulation that still alleges covert intentional coordination, tampering, cover-up, or secret organized wrongdoing.
4. **Other non-explicit claim**: the participant offers a different reformulation that does not allege covert intentional coordination and instead frames the issue in terms of irregularities, vulnerabilities, weak safeguards, isolated failures, background influence, or uncertainty.
5. **Unclassifiable or weakly ambiguous**: the transcript does not permit a reliable classification as either explicit or non-explicit.

Boundary rule for "explicitly conspiratorial":

- The clarified claim must attribute the event or outcome to intentional covert coordination, organized tampering, deliberate cover-up, or secret elite orchestration.

Boundary rule for "non-explicitly conspiratorial":

- The clarified claim may still express suspicion, concern, irregularity, vulnerability, negligence, isolated wrongdoing, or background influence, but it does not attribute the outcome to intentional covert coordination or secret organized orchestration.

For the primary H1 test, categories 1 and 3 will be collapsed into **explicitly conspiratorial**, and categories 2 and 4 will be collapsed into **non-explicitly conspiratorial**. Category 5 will be treated as analytically informative rather than discarded: it will be reported separately and incorporated into sensitivity analyses described below.

### Coding procedure

1. If the transcript makes the A/B choice explicit, that transcript will be coded accordingly unless the participant immediately revises the claim and the chatbot confirms a different clarified claim before the baseline confidence question.
2. If the participant offers their own wording, coding will be based on the clarified discussion claim actually confirmed before the discussion baseline rating.
3. Two human coders will independently code all participant-generated reformulations and any ambiguous A/B cases.
4. Coders will be blind to final confidence scores and, when feasible, to condition.
5. Disagreements will be resolved by discussion; if disagreement remains, a third coder will adjudicate.
6. Interrater agreement will be reported.
7. A short coding memo with worked examples and boundary cases will be frozen with the preregistered materials before confirmatory coding begins.

## Exclusion criteria

The following responses will be excluded from all confirmatory analyses:

1. Qualtrics preview responses.
2. Internal tests, debugging sessions, or any response collected before the preregistration timestamp.
3. Non-consenting respondents.
4. Duplicate responses from the same `ResponseId` or Prolific ID. If duplicates occur, the earliest non-preview response with `Finished = TRUE` will be retained, using Qualtrics recorded time to break ties.
5. Respondents who fail the instructed-response item in `QID224` ("There are many, please choose '4' for this statement.").

Additional outcome-specific exclusions:

1. Survey endline analyses require a non-missing `survey_claim_final_c`.

Responses will not be excluded solely for being fast. However, completion time will be summarized descriptively, and robustness checks excluding extremely fast respondents may be reported as exploratory if needed.

## Missing data and recovery rules

Because the chatbot stores both structured fields and full transcripts, the transcript will be treated as the authoritative backup when structured extraction fails.

Pre-specified recovery rules:

1. If `discussion_claim`, `discussion_claim_initial_credence`, or `discussion_claim_final_credence` is missing from structured chatbot output but is recoverable from the stored transcript, the missing value will be reconstructed from the transcript using the deterministic rules below.
2. Discussion baseline is defined as the participant's first 0-10 numeric answer to the chatbot's direct confidence question about the clarified discussion claim.
3. Discussion endline is defined as the participant's 0-10 numeric answer to the final confidence re-check about the clarified discussion claim.
4. If the participant stops early and no endline confidence rating is present in the transcript, that participant will remain in the primary H2 analysis with a conservative no-change imputation rule: discussion endline will be set equal to discussion baseline. The complete-case analysis will be reported as a sensitivity analysis.
5. If the clarified discussion claim cannot be recovered reliably, the case will be coded as unclassifiable for H1 rather than removed from the descriptive sample.
6. All transcript-based recovery and coding will be performed from de-identified transcript exports, and the recovery script or audit sheet will be archived with the OSF materials.

## Analysis plan

### H1

Primary H1 sample: all chatbot participants.

Primary H1 outcome:

- `1 = non-explicitly conspiratorial clarified claim`
- `0 = explicitly conspiratorial clarified claim`

Primary H1 test:

- Primary inferential test on classifiable cases: exact binomial test against 0.50.
- Null hypothesis: the probability of a non-conspiratorial clarified claim is less than or equal to 0.50.
- Alternative hypothesis: the probability of a non-conspiratorial clarified claim is greater than 0.50.
- Sensitivity analysis 1: repeat the test treating all unclassifiable cases as conspiratorial.
- Sensitivity analysis 2: repeat the test treating all unclassifiable cases as non-conspiratorial.

Reported quantities:

- proportion non-explicitly conspiratorial
- 95% confidence interval
- full descriptive breakdown across the five coding categories
- unclassifiable rate overall, by condition, and by target-item family

### H2

Primary H2 sample: all randomized chatbot participants with a recovered discussion baseline.

Outcome:

- `discussion_claim_final_credence`

Primary H2 test:

- OLS regression predicting discussion endline confidence from condition, discussion baseline confidence, and target-item family (election-related vs non-electoral), using HC2 robust standard errors.
- Condition will be coded so that a negative coefficient indicates lower adjusted endline confidence in the same-claim reflective chatbot condition than in the same-claim neutral chatbot control condition.
- The primary confirmatory dataset will use the conservative no-change imputation rule for missing discussion endlines described above.
- Sensitivity analyses will report the same model on complete cases only and the unadjusted change-score comparison by condition.

Reported quantities:

- treatment and control means at baseline and endline
- adjusted condition coefficient
- 95% confidence interval for the condition effect
- endline-missing rate overall and by condition

### Secondary analyses

Secondary analyses will be reported using descriptive statistics and, where appropriate, paired or between-group tests clearly labeled as secondary:

1. `discussion_claim_initial_credence - survey_claim_initial_credence`
2. `survey_claim_final_c - survey_claim_initial_credence`
3. `discussion_claim_final_credence - survey_claim_initial_credence`
4. Within-treatment change in `discussion_claim_final_credence - discussion_claim_initial_credence`

These secondary analyses will be stratified by condition when useful, but they will not be treated as the main confirmatory tests.

## Exploratory analyses

The following analyses will be labeled exploratory:

1. Moderation by exact claim content or claim family (election-related vs non-electoral).
2. Moderation by participant ideology or other background covariates from the Qualtrics survey.
3. Whether H2 effects vary by clarification category (A-consistent, B-consistent, other explicit, other non-explicit).
4. Whether survey-to-discussion shifts are larger for participants whose clarified claim is less conspiratorial than their original survey item.
5. Sensitivity analyses excluding very fast completions.

## Deviations from plan

Any departures from this preregistration will be documented explicitly in the manuscript and, where possible, in an OSF update that states what changed, when it changed, and why.

## Materials to archive with the registration

The following study materials will be attached or linked in OSF when this preregistration is filed:

- The active Qualtrics survey file.
- The chatbot system-message file containing the exact A/B prompts and control-condition instructions.
- The code used to merge Qualtrics and chatbot data.
- The code used to recover missing structured chatbot fields from transcripts, if applicable.
- The frozen analysis script, software environment, and package versions used for the confirmatory analyses.
