## ADDED Requirements

### Requirement: Per-session chat start time is recorded

The application SHALL record a `chat_started_at` field on the per-session MongoDB document the first time the participant sends a message in that session. The value SHALL be a UTC ISO 8601 timestamp. Once set, `chat_started_at` SHALL NOT be overwritten by subsequent turns within the same session.

#### Scenario: First user message sets the start time
- **WHEN** a participant sends their first message in a session
- **THEN** the session's MongoDB document has `chat_started_at` set to the current UTC timestamp in ISO 8601 form

#### Scenario: Subsequent user messages do not overwrite start time
- **WHEN** a participant sends a second or later message in the same session
- **THEN** the value of `chat_started_at` on the session document is unchanged from when it was first set

### Requirement: Per-session chat end time and duration are recorded

The application SHALL record a `chat_ended_at` field (UTC ISO 8601 timestamp) and a `chat_duration_seconds` field (number, rounded to the nearest second) on the per-session MongoDB document at the moment the chat ends — defined as the turn in which `input_active` transitions from 1 to 0 (the goodbye/handoff turn). `chat_duration_seconds` SHALL equal the integer seconds between `chat_started_at` and `chat_ended_at`. The end fields SHALL be written exactly once per session.

#### Scenario: Chat end populates end timestamp and duration
- **WHEN** the chat reaches its end state (the bot's response triggers `should_end_chat` and `input_active` becomes 0)
- **THEN** the session document has `chat_ended_at` set to the current UTC ISO 8601 timestamp and `chat_duration_seconds` set to the integer seconds elapsed since `chat_started_at`

#### Scenario: End fields stable across re-renders after chat end
- **WHEN** Streamlit re-runs the script after the chat has ended (e.g. for the inline return button render)
- **THEN** `chat_ended_at` and `chat_duration_seconds` on the session document retain the values from the original end turn and are not rewritten with new timestamps

### Requirement: Abandoned sessions have start time but no end fields

If a participant starts a chat but never reaches the end state, the application SHALL leave `chat_ended_at` and `chat_duration_seconds` unset on the session document. The application SHALL NOT write a synthetic end timestamp on session expiry, page refresh, or any path other than reaching the chat-end state.

#### Scenario: Abandoned session retains start only
- **WHEN** a participant sends a first message but never completes the chat
- **THEN** the session document has `chat_started_at` set, and `chat_ended_at` and `chat_duration_seconds` are absent (or null)
