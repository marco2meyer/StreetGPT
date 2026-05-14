import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


DEFAULT_QUALTRICS_PATH = "/Users/marco/Downloads/Election+issues_March+31,+2026_00.32.csv"
DEFAULT_MONGO_PATH = "/Users/marco/Downloads/streetgpt.conversations.json"


CLAIM_COLUMNS = {
    "non1_epstein": "Jeffrey Epstein, the billionaire accused of running an elite sex trafficking ring, was murdered to cover up the activities of his criminal network.",
    "non2_jfk": "There was a broad conspiracy, rather than a lone gunman, responsible for the assassination of President Kennedy.",
    "non3_vax": "The truth about the harmful effects of vaccines is being deliberately hidden from the public.",
    "non4_nwo": "Regardless of who is officially in charge of governments and other organizations, there is a single group of people who secretly control events and rule the world together.",
    "rep1_2020": "Election fraud was widespread enough to influence the outcome of the 2020 Presidential Elections in favor of Joe Biden.",
    "rep2_noncitizens": "Democrats organize non-citizens (e.g., undocumented immigrants) to vote illegally in U.S. elections to rig elections.",
    "rep3_mailmach": "Democrats commit widespread voter fraud in U.S. elections through manipulating mail-in voting and voting machines.",
    "dem1_elon": "Elon Musk's company, SpaceX, used its Starlink satellite technology to manipulate election results during the 2024 U.S. presidential election.",
    "dem2_russia": "Donald Trump's campaign team coordinated with the Russian government to interfere in the 2016 Presidential Election.",
    "dem3_elections": "Republicans won the presidential elections in 2016, 2004, and 2000 by stealing them.",
    "dem4_2024": "Election fraud was widespread enough to influence the outcome of the 2024 Presidential Elections in favor of Donald Trump.",
}


def parse_timestamp(value: str):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_numeric_rating(value):
    matches = re.findall(r"(?<!\d)(10|[0-9])(?!\d)", str(value or ""))
    if len(matches) != 1:
        return None
    parsed = int(matches[0])
    return parsed if 0 <= parsed <= 10 else None


def recover_final_credence(messages):
    for index in range(len(messages) - 1):
        current_message = messages[index]
        next_message = messages[index + 1]
        if current_message.get("role") != "assistant" or next_message.get("role") != "user":
            continue
        prompt = str(current_message.get("content") or "").lower()
        if "where would you now place your confidence" not in prompt:
            continue
        return parse_numeric_rating(next_message.get("content"))
    return None


def detect_stopped_early(messages):
    last_user_text = " ".join(
        str(message.get("content") or "").lower()
        for message in messages[-8:]
        if message.get("role") == "user"
    )
    return "stop for today" in last_user_text or re.search(r"\bpause\b", last_user_text) is not None


def count_error_messages(record):
    return str(record.get("error_messages") or "").count("responses_api_error")


def eligible_claims_from_row(row):
    claims = []
    for column, claim_text in CLAIM_COLUMNS.items():
        value = row.get(column, "")
        if pd.isna(value):
            continue
        try:
            score = int(str(value).strip())
        except ValueError:
            continue
        if score >= 6:
            claims.append({"column": column, "score": score, "claim": claim_text})
    return claims


@st.cache_data(show_spinner=False)
def load_qualtrics_csv(path_str: str):
    path = Path(path_str).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Qualtrics file not found: {path}")
    return pd.read_csv(path, skiprows=[1, 2], dtype=str).fillna("")


@st.cache_data(show_spinner=False)
def load_mongo_json(path_str: str):
    path = Path(path_str).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Mongo file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Expected a JSON list of conversation records.")
    return payload


def build_merged_dataframe(qual_df: pd.DataFrame, mongo_records: list[dict]):
    mongo_by_response_id = {record.get("session_id"): record for record in mongo_records}

    merged_rows = []
    for _, row in qual_df.iterrows():
        eligible_claims = eligible_claims_from_row(row)
        mongo_record = mongo_by_response_id.get(row.get("ResponseId"))
        quality_flags = []

        chat_status = "no_mongo_chat"
        mongo_discussion_claim = ""
        mongo_survey_claim = ""
        mongo_initial = ""
        mongo_final_raw = ""
        mongo_final_recovered = ""
        mongo_message_count = ""
        mongo_user_message_count = ""
        mongo_assistant_message_count = ""
        mongo_chat_minutes = ""
        mongo_error_count = ""

        if mongo_record:
            messages = mongo_record.get("messages", [])
            recovered_final = recover_final_credence(messages)
            raw_final = mongo_record.get("discussion_claim_final_credence")

            mongo_discussion_claim = mongo_record.get("discussion_claim") or ""
            mongo_survey_claim = mongo_record.get("survey_claim") or ""
            mongo_initial = mongo_record.get("discussion_claim_initial_credence")
            mongo_final_raw = raw_final if raw_final is not None else ""
            mongo_final_recovered = recovered_final if recovered_final is not None else ""
            mongo_message_count = len(messages)
            mongo_user_message_count = sum(1 for message in messages if message.get("role") == "user")
            mongo_assistant_message_count = sum(1 for message in messages if message.get("role") == "assistant")
            mongo_error_count = count_error_messages(mongo_record)

            created_at = parse_timestamp(mongo_record.get("created_at", ""))
            updated_at = parse_timestamp(mongo_record.get("updated_at", ""))
            if created_at and updated_at:
                mongo_chat_minutes = round((updated_at - created_at).total_seconds() / 60, 2)

            if recovered_final is not None:
                chat_status = "completed_with_recoverable_endline"
                if raw_final is None:
                    quality_flags.append("mongo_final_credence_missing_but_recoverable")
            elif detect_stopped_early(messages):
                chat_status = "stopped_early_in_chat"
                quality_flags.append("chat_stopped_before_endline")
            else:
                chat_status = "mongo_chat_present_but_no_recoverable_endline"
                quality_flags.append("mongo_chat_missing_endline")
        else:
            if eligible_claims:
                chat_status = "expected_chat_but_missing_in_mongo"
                quality_flags.append("eligible_for_chat_but_no_mongo_record")
            else:
                chat_status = "no_chat_expected_no_eligible_claims"

        try:
            duration_seconds = int(str(row.get("Duration (in seconds)", "0")).strip() or 0)
        except ValueError:
            duration_seconds = 0

        if duration_seconds < 120:
            quality_flags.append("extremely_fast_completion")

        if not str(row.get("control_flag", "")).strip():
            quality_flags.append("missing_control_fields_in_qualtrics")

        if eligible_claims and not mongo_record and duration_seconds < 120:
            quality_flags.append("likely_invalid_or_broken_response")

        qualtrics_chat_fields = [
            row.get("survey_claim", ""),
            row.get("discussion_claim", ""),
            row.get("discussion_claim_initial_credence", ""),
            row.get("discussion_claim_final_credence", ""),
        ]
        if any(not str(value).strip() for value in qualtrics_chat_fields):
            quality_flags.append("qualtrics_chat_embedded_data_blank")

        merged_row = row.to_dict()
        merged_row.update(
            {
                "join_has_mongo_chat": bool(mongo_record),
                "join_chat_status": chat_status,
                "derived_eligible_claim_count": len(eligible_claims),
                "derived_eligible_claim_scores": " | ".join(
                    f"{claim['column']}={claim['score']}" for claim in eligible_claims
                ),
                "derived_eligible_claim_texts": "\n\n".join(
                    f"{claim['column']} ({claim['score']}): {claim['claim']}" for claim in eligible_claims
                ),
                "mongo_discussion_claim": mongo_discussion_claim,
                "mongo_survey_claim": mongo_survey_claim,
                "mongo_discussion_claim_initial_credence": mongo_initial,
                "mongo_discussion_claim_final_credence_raw": mongo_final_raw,
                "mongo_discussion_claim_final_credence_recovered": mongo_final_recovered,
                "mongo_message_count": mongo_message_count,
                "mongo_user_message_count": mongo_user_message_count,
                "mongo_assistant_message_count": mongo_assistant_message_count,
                "mongo_chat_minutes": mongo_chat_minutes,
                "mongo_error_count": mongo_error_count,
                "quality_flags": " | ".join(quality_flags),
                "_eligible_claims": eligible_claims,
                "_mongo_record": mongo_record,
            }
        )
        merged_rows.append(merged_row)

    merged_df = pd.DataFrame(merged_rows)
    if "RecordedDate" in merged_df.columns:
        merged_df = merged_df.sort_values("RecordedDate")
    return merged_df


def classify_real_rows(df: pd.DataFrame):
    real_mask = (
        (df["DistributionChannel"] != "preview")
        & (~df["PROLIFIC_PID"].fillna("").str.startswith("TEST_"))
        & (df["PROLIFIC_PID"].fillna("").str.strip() != "")
    )
    return df.loc[real_mask].copy()


def render_transcript(messages):
    if not messages:
        st.info("No Mongo transcript available for this row.")
        return
    for message in messages:
        role = message.get("role", "assistant")
        label = "User" if role == "user" else "Assistant"
        timestamp = message.get("ts", "")
        with st.chat_message("user" if role == "user" else "assistant"):
            if timestamp:
                st.caption(timestamp)
            st.markdown(f"**{label}**")
            st.write(message.get("content", ""))


def main():
    st.set_page_config(page_title="StreetGPT Combined Viewer", layout="wide")
    st.title("StreetGPT Combined Response Viewer")
    st.caption("Join Qualtrics export rows with Mongo chat records, surface quality issues, and inspect transcripts.")

    with st.sidebar:
        st.header("Sources")
        qualtrics_path = st.text_input("Qualtrics CSV", value=DEFAULT_QUALTRICS_PATH)
        mongo_path = st.text_input("Mongo JSON", value=DEFAULT_MONGO_PATH)
        include_tests = st.checkbox("Include test respondents", value=False)
        include_preview = st.checkbox("Include preview rows", value=False)
        only_flagged = st.checkbox("Only show rows with quality flags", value=False)

    try:
        qualtrics_df = load_qualtrics_csv(qualtrics_path)
        mongo_records = load_mongo_json(mongo_path)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    merged_df = build_merged_dataframe(qualtrics_df, mongo_records)
    view_df = merged_df.copy()

    if not include_preview:
        view_df = view_df.loc[view_df["DistributionChannel"] != "preview"]
    if not include_tests:
        view_df = view_df.loc[~view_df["PROLIFIC_PID"].fillna("").str.startswith("TEST_")]
    if only_flagged:
        view_df = view_df.loc[view_df["quality_flags"].fillna("").str.strip() != ""]

    status_options = ["All"] + sorted(view_df["join_chat_status"].dropna().unique().tolist())
    selected_status = st.selectbox("Filter by chat status", options=status_options, index=0)
    if selected_status != "All":
        view_df = view_df.loc[view_df["join_chat_status"] == selected_status]

    real_non_test_df = classify_real_rows(merged_df)
    recoverable_mask = (
        real_non_test_df["mongo_discussion_claim_final_credence_raw"].astype(str).str.strip().eq("")
        & real_non_test_df["mongo_discussion_claim_final_credence_recovered"].astype(str).str.strip().ne("")
    )

    metric_cols = st.columns(5)
    metric_cols[0].metric("Real non-test rows", int(len(real_non_test_df)))
    metric_cols[1].metric("Mongo chats", int(real_non_test_df["join_has_mongo_chat"].sum()))
    metric_cols[2].metric(
        "Missing Mongo chats",
        int((~real_non_test_df["join_has_mongo_chat"]).sum()),
    )
    metric_cols[3].metric("Recoverable endlines", int(recoverable_mask.sum()))
    metric_cols[4].metric(
        "Stopped early chats",
        int((real_non_test_df["join_chat_status"] == "stopped_early_in_chat").sum()),
    )

    st.subheader("Overview")
    overview_columns = [
        "ResponseId",
        "PROLIFIC_PID",
        "RecordedDate",
        "Duration (in seconds)",
        "join_has_mongo_chat",
        "join_chat_status",
        "derived_eligible_claim_scores",
        "mongo_discussion_claim_initial_credence",
        "mongo_discussion_claim_final_credence_raw",
        "mongo_discussion_claim_final_credence_recovered",
        "quality_flags",
    ]
    st.dataframe(
        view_df[overview_columns],
        use_container_width=True,
        hide_index=True,
    )

    export_df = view_df.drop(columns=["_mongo_record", "_eligible_claims"], errors="ignore")
    st.download_button(
        "Download current view as CSV",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name="streetgpt_combined_view.csv",
        mime="text/csv",
    )

    st.subheader("Row Inspector")
    response_ids = view_df["ResponseId"].dropna().tolist()
    if not response_ids:
        st.info("No rows match the current filters.")
        return

    selected_response_id = st.selectbox("Select a response", options=response_ids)
    selected_row = view_df.loc[view_df["ResponseId"] == selected_response_id].iloc[0]

    left_col, right_col = st.columns([1, 1])
    with left_col:
        st.markdown("**Joined Summary**")
        st.json(
            {
                "ResponseId": selected_row["ResponseId"],
                "PROLIFIC_PID": selected_row["PROLIFIC_PID"],
                "SESSION_ID": selected_row["SESSION_ID"],
                "RecordedDate": selected_row["RecordedDate"],
                "duration_seconds": selected_row["Duration (in seconds)"],
                "join_chat_status": selected_row["join_chat_status"],
                "eligible_claim_count": int(selected_row["derived_eligible_claim_count"]),
                "eligible_claim_scores": selected_row["derived_eligible_claim_scores"],
                "quality_flags": selected_row["quality_flags"],
            }
        )

        st.markdown("**Qualtrics vs Mongo Chat Fields**")
        comparison_df = pd.DataFrame(
            [
                {
                    "field": "survey_claim",
                    "qualtrics": selected_row.get("survey_claim", ""),
                    "mongo_or_recovered": selected_row.get("mongo_survey_claim", ""),
                },
                {
                    "field": "discussion_claim",
                    "qualtrics": selected_row.get("discussion_claim", ""),
                    "mongo_or_recovered": selected_row.get("mongo_discussion_claim", ""),
                },
                {
                    "field": "discussion_claim_initial_credence",
                    "qualtrics": selected_row.get("discussion_claim_initial_credence", ""),
                    "mongo_or_recovered": selected_row.get("mongo_discussion_claim_initial_credence", ""),
                },
                {
                    "field": "discussion_claim_final_credence",
                    "qualtrics": selected_row.get("discussion_claim_final_credence", ""),
                    "mongo_or_recovered": (
                        selected_row.get("mongo_discussion_claim_final_credence_raw", "")
                        or selected_row.get("mongo_discussion_claim_final_credence_recovered", "")
                    ),
                },
            ]
        )
        st.dataframe(comparison_df, use_container_width=True, hide_index=True)

    with right_col:
        st.markdown("**Eligible Claims From Survey Answers**")
        eligible_claims = selected_row.get("_eligible_claims", [])
        if eligible_claims:
            for claim in eligible_claims:
                st.markdown(f"- `{claim['column']} = {claim['score']}`")
                st.write(claim["claim"])
        else:
            st.info("No claims scored >= 6, so no chatbot was expected.")

        st.markdown("**Mongo Record Snapshot**")
        mongo_record = selected_row.get("_mongo_record")
        if mongo_record:
            st.json(
                {
                    "session_id": mongo_record.get("session_id"),
                    "prolific_pid": mongo_record.get("prolific_pid"),
                    "prolific_session_id": mongo_record.get("prolific_session_id"),
                    "study_id": mongo_record.get("study_id"),
                    "survey_claim": mongo_record.get("survey_claim"),
                    "discussion_claim": mongo_record.get("discussion_claim"),
                    "discussion_claim_initial_credence": mongo_record.get("discussion_claim_initial_credence"),
                    "discussion_claim_final_credence": mongo_record.get("discussion_claim_final_credence"),
                    "error_count": count_error_messages(mongo_record),
                    "updated_at": mongo_record.get("updated_at"),
                }
            )
        else:
            st.info("No Mongo record matched this response.")

    st.subheader("Transcript")
    render_transcript((selected_row.get("_mongo_record") or {}).get("messages", []))


if __name__ == "__main__":
    main()
