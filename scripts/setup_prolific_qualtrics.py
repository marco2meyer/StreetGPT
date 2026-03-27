#!/usr/bin/env python3
"""Prepare a Qualtrics QSF for Prolific and optionally create a Prolific study."""

from __future__ import annotations

import argparse
import json
import re
import secrets
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests


COMPLETE_CODE_PLACEHOLDER = "PROLIFIC-COMPLETE-CODE"
SCREENOUT_CODE_PLACEHOLDER = "PROLIFIC-SCREENOUT-CODE"
POOR_QUALITY_CODE_PLACEHOLDER = "PROLIFIC-POOR-QUALITY-CODE"
PROLIFIC_COMPLETE_URL = "https://app.prolific.com/submissions/complete?cc={code}"
PROLIFIC_API_URL = "https://api.prolific.com/api/v1"
DEFAULT_DEVICE_COMPATIBILITY = ["desktop", "mobile", "tablet"]


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def slugify_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return slug or "study"


def make_completion_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


def normalize_public_chatbot_url(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise ValueError("CHATBOT_PUBLIC_URL or SITE_HOST must be set")

    if "://" not in value:
        if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", value):
            value = f"{value.replace('.', '-')}.sslip.io"
        value = f"https://{value}"

    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Unable to build a public chatbot URL from {raw_value!r}")

    hostname = parsed.hostname or ""
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", hostname):
        replacement_host = f"{hostname.replace('.', '-')}.sslip.io"
        value = value.replace(hostname, replacement_host, 1)

    return value.rstrip("/") + "/"


def build_external_study_url(qualtrics_url: str) -> str:
    separators = "&" if "?" in qualtrics_url else "?"
    params = [
        ("PROLIFIC_PID", "{{%PROLIFIC_PID%}}"),
        ("STUDY_ID", "{{%STUDY_ID%}}"),
        ("SESSION_ID", "{{%SESSION_ID%}}"),
    ]
    suffix = "&".join(
        f"{quote(key, safe='')}={quote(value, safe='{}%')}" for key, value in params
    )
    return f"{qualtrics_url}{separators}{suffix}"


def strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def derive_intro_description(qsf: dict[str, Any]) -> str:
    for element in qsf.get("SurveyElements", []):
        if element.get("Element") != "SQ":
            continue
        payload = element.get("Payload", {})
        if element.get("PrimaryAttribute") == "QID98":
            text = strip_html(payload.get("QuestionText", ""))
            return text[:1000]
    survey_name = qsf.get("SurveyEntry", {}).get("SurveyName", "Qualtrics study")
    return f"Please complete the Qualtrics survey titled '{survey_name}'."


def extract_existing_chatbot_url(qsf_path: Path) -> str:
    qsf = json.loads(qsf_path.read_text(encoding="utf-8"))
    question = find_question(qsf, "QID399")
    question_js = question.get("Payload", {}).get("QuestionJS", "")
    match = re.search(r'var CHATBOT_BASE_URL = "([^"]+)";', question_js)
    if not match:
        return ""
    return match.group(1)


def derive_estimated_minutes(qsf: dict[str, Any], fallback: int) -> int:
    for element in qsf.get("SurveyElements", []):
        if element.get("PrimaryAttribute") != "QID98":
            continue
        payload = element.get("Payload", {})
        question_text = strip_html(payload.get("QuestionText", ""))
        match = re.search(r"(\d+)\s+minutes?", question_text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return fallback


def find_survey_flow(qsf: dict[str, Any]) -> dict[str, Any]:
    for element in qsf.get("SurveyElements", []):
        if element.get("Element") == "FL":
            return element
    raise ValueError("Could not find the Qualtrics survey flow in the QSF")


def find_question(qsf: dict[str, Any], qid: str) -> dict[str, Any]:
    for element in qsf.get("SurveyElements", []):
        if element.get("Element") == "SQ" and element.get("PrimaryAttribute") == qid:
            return element
    raise ValueError(f"Could not find question {qid} in the QSF")


def ensure_embedded_data_fields(flow_element: dict[str, Any], field_names: list[str]) -> None:
    flow_payload = flow_element.get("Payload", {})
    flow_items = flow_payload.get("Flow", [])
    if not flow_items or flow_items[0].get("Type") != "EmbeddedData":
        raise ValueError("Expected the first survey flow item to be an EmbeddedData block")

    embedded_items = flow_items[0].setdefault("EmbeddedData", [])
    existing_fields = {item.get("Field") for item in embedded_items}
    prolific_index = next(
        (index for index, item in enumerate(embedded_items) if item.get("Field") == "PROLIFIC_PID"),
        len(embedded_items) - 1,
    )
    insert_at = prolific_index + 1

    for field_name in field_names:
        if field_name in existing_fields:
            continue
        embedded_items.insert(
            insert_at,
            {
                "Description": field_name,
                "Type": "Recipient",
                "Field": field_name,
                "VariableType": "String",
                "DataVisibility": [],
                "AnalyzeText": False,
            },
        )
        insert_at += 1
        existing_fields.add(field_name)


def patch_prolific_redirects(qsf: dict[str, Any], codes: dict[str, str]) -> None:
    survey_flow = find_survey_flow(qsf)

    def patch_flow_items(items: list[dict[str, Any]]) -> None:
        for item in items:
            if item.get("Type") == "EndSurvey":
                options = item.setdefault("Options", {})
                response_flag = options.get("ResponseFlag")
                if response_flag == "Screened":
                    options["EOSRedirectURL"] = PROLIFIC_COMPLETE_URL.format(code=codes["screenout"])
                elif response_flag == "PoorQuality":
                    options["EOSRedirectURL"] = PROLIFIC_COMPLETE_URL.format(code=codes["poor_quality"])
            if "Flow" in item and isinstance(item["Flow"], list):
                patch_flow_items(item["Flow"])

    patch_flow_items(survey_flow.get("Payload", {}).get("Flow", []))

    for element in qsf.get("SurveyElements", []):
        if element.get("Element") == "SO":
            payload = element.setdefault("Payload", {})
            payload["EOSRedirectURL"] = PROLIFIC_COMPLETE_URL.format(code=codes["complete"])
            break


def patch_chatbot_question_js(question_js: str, chatbot_url: str, password: str) -> str:
    updated = re.sub(
        r'var CHATBOT_BASE_URL = "[^"]+";',
        f'var CHATBOT_BASE_URL = {json.dumps(chatbot_url)};',
        question_js,
        count=1,
    )
    updated = re.sub(
        r'var PASSWORD = "[^"]+";',
        f'var PASSWORD = {json.dumps(password)};',
        updated,
        count=1,
    )

    prolific_pid_line = '  var PROLIFIC_PID = "${e://Field/PROLIFIC_PID}";\n'
    study_session_lines = (
        '  var STUDY_ID = "${e://Field/STUDY_ID}";\n'
        '  var SESSION_ID = "${e://Field/SESSION_ID}";\n'
    )
    if 'var STUDY_ID = "${e://Field/STUDY_ID}";' not in updated:
        updated = updated.replace(prolific_pid_line, prolific_pid_line + study_session_lines, 1)

    prolific_pid_block = (
        '    if (PROLIFIC_PID) {\n'
        '      chatbotUrl.searchParams.set("prolific_pid", PROLIFIC_PID);\n'
        '    }\n'
    )
    extra_prolific_context = (
        '    if (STUDY_ID) {\n'
        '      chatbotUrl.searchParams.set("study_id", STUDY_ID);\n'
        '    }\n'
        '    if (SESSION_ID) {\n'
        '      chatbotUrl.searchParams.set("session_id", SESSION_ID);\n'
        '    }\n'
    )
    if 'chatbotUrl.searchParams.set("study_id", STUDY_ID);' not in updated:
        updated = updated.replace(prolific_pid_block, prolific_pid_block + extra_prolific_context, 1)

    return updated


def prepare_qsf(
    qsf_path: Path,
    output_path: Path,
    chatbot_url: str,
    password: str,
    codes: dict[str, str],
) -> dict[str, Any]:
    qsf = json.loads(qsf_path.read_text(encoding="utf-8"))
    survey_flow = find_survey_flow(qsf)
    ensure_embedded_data_fields(survey_flow, ["STUDY_ID", "SESSION_ID"])
    patch_prolific_redirects(qsf, codes)

    chatbot_question = find_question(qsf, "QID399")
    payload = chatbot_question.setdefault("Payload", {})
    payload["QuestionJS"] = patch_chatbot_question_js(
        payload.get("QuestionJS", ""),
        chatbot_url,
        password,
    )

    output_path.write_text(compact_json(qsf), encoding="utf-8")
    return qsf


def build_completion_codes(args: argparse.Namespace) -> dict[str, str]:
    return {
        "complete": args.complete_code or make_completion_code(),
        "screenout": args.screenout_code or make_completion_code(),
        "poor_quality": args.poor_quality_code or make_completion_code(),
    }


def make_prolific_completion_actions(
    code_type: str,
    *,
    screenout_reward: int | None = None,
    screenout_slots: int | None = None,
    auto_approve: bool = False,
) -> list[dict[str, Any]]:
    if code_type == "SCREENED_OUT" and screenout_reward is not None:
        if screenout_slots is None:
            raise ValueError("screenout_slots is required when screenout_reward is set")
        return [
            {
                "action": "FIXED_SCREEN_OUT_PAYMENT",
                "fixed_screen_out_reward": screenout_reward,
                "slots": screenout_slots,
            }
        ]

    action = "AUTOMATICALLY_APPROVE" if auto_approve else "MANUALLY_REVIEW"
    return [{"action": action}]


def build_study_payload(
    args: argparse.Namespace,
    qsf: dict[str, Any],
    external_study_url: str,
    codes: dict[str, str],
) -> dict[str, Any]:
    survey_name = qsf.get("SurveyEntry", {}).get("SurveyName", "Qualtrics study")
    estimated_minutes = args.estimated_completion_time or derive_estimated_minutes(qsf, 20)
    description = args.description or derive_intro_description(qsf)

    payload: dict[str, Any] = {
        "name": args.study_name or survey_name,
        "internal_name": args.internal_name or survey_name,
        "description": description,
        "external_study_url": external_study_url,
        "prolific_id_option": "url_parameters",
        "estimated_completion_time": estimated_minutes,
        "device_compatibility": args.device_compatibility or DEFAULT_DEVICE_COMPATIBILITY,
        "completion_codes": [
            {
                "code": codes["complete"],
                "code_type": "COMPLETED",
                "actions": make_prolific_completion_actions(
                    "COMPLETED",
                    auto_approve=args.auto_approve,
                ),
            },
            {
                "code": codes["screenout"],
                "code_type": "SCREENED_OUT",
                "actions": make_prolific_completion_actions(
                    "SCREENED_OUT",
                    screenout_reward=args.screenout_reward,
                    screenout_slots=args.screenout_slots,
                ),
            },
            {
                "code": codes["poor_quality"],
                "code_type": "SCREENED_OUT",
                "actions": make_prolific_completion_actions("SCREENED_OUT"),
            },
        ],
        "filters": args.filters or [],
    }

    if args.maximum_allowed_time is not None:
        payload["maximum_allowed_time"] = args.maximum_allowed_time
    elif estimated_minutes:
        payload["maximum_allowed_time"] = max(estimated_minutes * 3, estimated_minutes + 10)

    if args.reward is not None:
        payload["reward"] = args.reward
    if args.total_available_places is not None:
        payload["total_available_places"] = args.total_available_places
    if args.study_label:
        payload["study_labels"] = [args.study_label]
    if args.project_id:
        payload["project"] = args.project_id

    return payload


def prolific_request(method: str, token: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }
    response = requests.request(
        method,
        f"{PROLIFIC_API_URL}{path}",
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    if response.content:
        return response.json()
    return {}


def require_token(args: argparse.Namespace, env: dict[str, str]) -> str:
    token = (args.prolific_token or env.get("PROLIFIC_API", "")).strip()
    if not token:
        raise ValueError("PROLIFIC_API is missing. Add it to .env or pass --prolific-token.")
    return token


def write_setup_summary(summary_path: Path, summary: dict[str, Any]) -> None:
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch a Qualtrics QSF for Prolific and optionally create a Prolific study.",
    )
    parser.add_argument(
        "--qsf",
        default="election_conspiracy_experiment_files/2025_American_Survey_-_AI_ChatBot (1).qsf",
        help="Input Qualtrics QSF file.",
    )
    parser.add_argument(
        "--output",
        help="Output QSF path. Defaults to a sibling file ending in .prolific_ready.qsf.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file with PASSWORD, SITE_HOST/CHATBOT_PUBLIC_URL, and PROLIFIC_API.",
    )
    parser.add_argument("--qualtrics-url", help="Live anonymous Qualtrics survey URL.")
    parser.add_argument("--chatbot-url", help="Explicit public StreetGPT URL.")
    parser.add_argument("--password", help="StreetGPT URL password override.")
    parser.add_argument("--prolific-token", help="Prolific API token override.")
    parser.add_argument("--study-name", help="Participant-facing Prolific study name.")
    parser.add_argument("--internal-name", help="Internal Prolific study name.")
    parser.add_argument("--description", help="Participant-facing Prolific description.")
    parser.add_argument("--estimated-completion-time", type=int, help="Estimated completion time in minutes.")
    parser.add_argument("--maximum-allowed-time", type=int, help="Maximum allowed time in minutes.")
    parser.add_argument("--reward", type=int, help="Reward in the smallest Prolific currency unit.")
    parser.add_argument("--total-available-places", type=int, help="Number of participant slots.")
    parser.add_argument(
        "--device-compatibility",
        nargs="+",
        help="Values like desktop mobile tablet. Defaults to desktop mobile tablet.",
    )
    parser.add_argument("--study-label", help="Optional Prolific study label, for example survey or interview.")
    parser.add_argument("--project-id", help="Optional Prolific project id.")
    parser.add_argument("--screenout-reward", type=int, help="Fixed screen-out reward in the smallest currency unit.")
    parser.add_argument("--screenout-slots", type=int, help="How many screen-out slots to reserve.")
    parser.add_argument("--complete-code", help="Override the completed submission code.")
    parser.add_argument("--screenout-code", help="Override the screen-out submission code.")
    parser.add_argument("--poor-quality-code", help="Override the poor-quality submission code.")
    parser.add_argument("--auto-approve", action="store_true", help="Automatically approve completed submissions.")
    parser.add_argument("--create-study", action="store_true", help="Create a Prolific draft study through the API.")
    parser.add_argument("--publish-study", action="store_true", help="Publish the created study after draft creation.")
    parser.add_argument("--validate-token", action="store_true", help="Validate the Prolific API token.")
    parser.add_argument("--filters", type=json.loads, help="Optional raw JSON array of Prolific filters.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = load_env_file(Path(args.env_file))

    qsf_path = Path(args.qsf)
    if not qsf_path.exists():
        raise FileNotFoundError(f"QSF file not found: {qsf_path}")

    default_output = qsf_path.with_name(f"{qsf_path.stem}.prolific_ready{qsf_path.suffix}")
    output_path = Path(args.output) if args.output else default_output

    password = (args.password or env.get("PASSWORD", "")).strip()
    if not password:
        raise ValueError("PASSWORD is missing. Add it to .env or pass --password.")

    existing_chatbot_url = extract_existing_chatbot_url(qsf_path)
    chatbot_url = normalize_public_chatbot_url(
        args.chatbot_url
        or env.get("CHATBOT_PUBLIC_URL", "")
        or env.get("SITE_HOST", "")
        or existing_chatbot_url
    )
    codes = build_completion_codes(args)
    qsf = prepare_qsf(qsf_path, output_path, chatbot_url, password, codes)

    qualtrics_url = (args.qualtrics_url or env.get("QUALTRICS_SURVEY_URL", "")).strip()
    external_study_url = build_external_study_url(qualtrics_url) if qualtrics_url else ""
    payload = build_study_payload(args, qsf, external_study_url, codes) if external_study_url else None

    summary_path = output_path.with_name(f"{slugify_filename(output_path.stem)}.setup.json")
    summary: dict[str, Any] = {
        "input_qsf": str(qsf_path),
        "output_qsf": str(output_path),
        "chatbot_public_url": chatbot_url,
        "qualtrics_url": qualtrics_url or None,
        "external_study_url": external_study_url or None,
        "completion_codes": codes,
        "prolific_payload": payload,
        "prolific_result": None,
        "published": False,
    }

    token: str | None = None
    if args.validate_token or args.create_study:
        token = require_token(args, env)

    if args.validate_token and token:
        summary["token_check"] = prolific_request("GET", token, "/workspaces/")

    if args.create_study:
        if not external_study_url:
            raise ValueError("A live Qualtrics URL is required to create a Prolific study.")
        if args.reward is None or args.total_available_places is None:
            raise ValueError("--reward and --total-available-places are required when --create-study is used.")
        result = prolific_request("POST", token, "/studies/", payload)
        summary["prolific_result"] = result
        if args.publish_study:
            prolific_request("POST", token, f"/studies/{result['id']}/transition/", {"action": "PUBLISH"})
            summary["published"] = True

    write_setup_summary(summary_path, summary)

    print(f"Patched QSF written to: {output_path}")
    print(f"Setup summary written to: {summary_path}")
    print(f"Chatbot public URL: {chatbot_url}")
    print(f"Completed code: {codes['complete']}")
    print(f"Screen-out code: {codes['screenout']}")
    print(f"Poor-quality code: {codes['poor_quality']}")
    if external_study_url:
        print(f"Prolific external study URL: {external_study_url}")
    else:
        print("Prolific external study URL: <missing Qualtrics URL>")
    if summary["prolific_result"]:
        print(f"Created Prolific study id: {summary['prolific_result']['id']}")
        print(f"Study status: {summary['prolific_result'].get('status')}")
    if summary["published"]:
        print("Study publish action: PUBLISH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
