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
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"))


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
    try:
        question = find_question(qsf, "QID399")
    except ValueError:
        return ""
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


def find_chatbot_block(qsf: dict[str, Any]) -> dict[str, Any]:
    blocks_element = next(
        (element for element in qsf.get("SurveyElements", []) if element.get("Element") == "BL"),
        None,
    )
    if not blocks_element:
        raise ValueError("Could not find the Qualtrics block payload in the QSF")

    payload = blocks_element.get("Payload", {})
    for block in payload.values():
        if not isinstance(block, dict):
            continue
        if block.get("ID") == "BL_0eOlvXtb4Or1i1o" or block.get("Description") == "AI Chat Bot -- Redirection":
            return block
    raise ValueError("Could not find the AI Chat Bot -- Redirection block in the QSF")


def make_embedded_data_field(
    field_name: str,
    variable_type: str = "String",
    *,
    analyze_text: bool | None = False,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "Description": field_name,
        "Type": "Recipient",
        "Field": field_name,
        "VariableType": variable_type,
        "DataVisibility": [],
    }
    if variable_type == "String":
        field["AnalyzeText"] = bool(analyze_text)
    return field


def ensure_embedded_data_fields(flow_element: dict[str, Any], field_specs: list[dict[str, Any]]) -> None:
    flow_payload = flow_element.get("Payload", {})
    flow_items = flow_payload.get("Flow", [])
    if not flow_items or flow_items[0].get("Type") != "EmbeddedData":
        raise ValueError("Expected the first survey flow item to be an EmbeddedData block")

    embedded_items = flow_items[0].setdefault("EmbeddedData", [])
    existing_fields = {item.get("Field") for item in embedded_items}
    for field_spec in field_specs:
        field_name = field_spec["Field"]
        if field_name in existing_fields:
            continue
        embedded_items.append(field_spec)
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


def build_chatbot_question_js(chatbot_url: str, password: str) -> str:
    return "\n".join(
        [
            "Qualtrics.SurveyEngine.addOnReady(function() {",
            f"  var CHATBOT_BASE_URL = {json.dumps(chatbot_url)};",
            f"  var PASSWORD = {json.dumps(password)};",
            '  var RESPONSE_ID = "${e://Field/ResponseID}";',
            '  var PROLIFIC_PID = "${e://Field/PROLIFIC_PID}";',
            '  var STUDY_ID = "${e://Field/STUDY_ID}";',
            '  var SESSION_ID = "${e://Field/SESSION_ID}";',
            "",
            "  function readEmbedded(name) {",
            "    var value = Qualtrics.SurveyEngine.getJSEmbeddedData(name);",
            '    return value == null ? "" : String(value);',
            "  }",
            "",
            "  function writeEmbedded(name, value) {",
            '    Qualtrics.SurveyEngine.setJSEmbeddedData(name, value == null ? "" : String(value));',
            "  }",
            "",
            '  var CONTROL_FLAG = readEmbedded("control_flag");',
            '  var CONTROL_CLAIM = readEmbedded("control_claim");',
            "",
            "  function readQueryParam(name) {",
            "    return new URL(window.location.href).searchParams.get(name) || \"\";",
            "  }",
            "",
            "  function parseScore(value) {",
            "    var parsed = parseInt(String(value || \"\").trim(), 10);",
            "    return isNaN(parsed) ? null : parsed;",
            "  }",
            "",
            "  function clickNext() {",
            '    var nextButton = document.getElementById("NextButton");',
            "    if (nextButton) {",
            "      nextButton.click();",
            "    }",
            "  }",
            "",
            "  function buildEligibleClaims() {",
            "    var claims = [];",
            "",
            "    function maybeAdd(score, claim, sourceQid) {",
            "      if (score === null || score < 6) {",
            "        return;",
            "      }",
            "      claims.push({ survey_claim: claim, survey_claim_initial_credence: score, survey_claim_source_qid: sourceQid });",
            "    }",
            "",
            '    maybeAdd(parseScore("${q://QID224/SelectedAnswerRecode/2}"), "Election fraud was widespread enough to influence the outcome of the 2020 Presidential Elections in favor of Joe Biden.", "QID224/2");',
            '    maybeAdd(parseScore("${q://QID224/SelectedAnswerRecode/8}"), "Democrats organize non-citizens (e.g., undocumented immigrants) to vote illegally in U.S. elections to rig elections.", "QID224/8");',
            '    maybeAdd(parseScore("${q://QID224/SelectedAnswerRecode/10}"), "Democrats commit widespread voter fraud in U.S. elections through manipulating mail-in voting and voting machines.", "QID224/10");',
            "",
            "    maybeAdd(parseScore(\"${q://QID272/SelectedAnswerRecode/1}\"), \"Elon Musk's company, SpaceX, used its Starlink satellite technology to manipulate election results during the 2024 U.S. presidential election.\", \"QID272/1\");",
            "    maybeAdd(parseScore(\"${q://QID272/SelectedAnswerRecode/2}\"), \"Donald Trump's campaign team coordinated with the Russian government to interfere in the 2016 Presidential Election.\", \"QID272/2\");",
            '    maybeAdd(parseScore("${q://QID272/SelectedAnswerRecode/3}"), "Republicans won the presidential elections in 2016, 2004, and 2000 by stealing them.", "QID272/3");',
            "",
            '    maybeAdd(parseScore("${q://QID342/SelectedAnswerRecode/1}"), "Jeffrey Epstein, the billionaire accused of running an elite sex trafficking ring, was murdered to cover up the activities of his criminal network.", "QID342/1");',
            '    maybeAdd(parseScore("${q://QID342/SelectedAnswerRecode/3}"), "There was a broad conspiracy, rather than a lone gunman, responsible for the assassination of President Kennedy.", "QID342/3");',
            '    maybeAdd(parseScore("${q://QID342/SelectedAnswerRecode/4}"), "The truth about the harmful effects of vaccines is being deliberately hidden from the public.", "QID342/4");',
            '    maybeAdd(parseScore("${q://QID342/SelectedAnswerRecode/5}"), "Regardless of who is officially in charge of governments and other organizations, there is a single group of people who secretly control events and rule the world together.", "QID342/5");',
            "",
            "    return claims;",
            "  }",
            "",
            "  function buildReturnUrl() {",
            "    var returnUrl = new URL(window.location.href);",
            '    returnUrl.searchParams.set("chat_return", "1");',
            "    if (PROLIFIC_PID) {",
            '      returnUrl.searchParams.set("PROLIFIC_PID", PROLIFIC_PID);',
            "    }",
            "    if (STUDY_ID) {",
            '      returnUrl.searchParams.set("STUDY_ID", STUDY_ID);',
            "    }",
            "    if (SESSION_ID) {",
            '      returnUrl.searchParams.set("SESSION_ID", SESSION_ID);',
            "    }",
            "    return returnUrl.toString();",
            "  }",
            "",
            "  function buildChatbotUrl(selected, returnUrl) {",
            "    var chatbotUrl = new URL(CHATBOT_BASE_URL);",
            "    var launchNonce = String(Date.now());",
            '    chatbotUrl.searchParams.set("password", PASSWORD);',
            '    chatbotUrl.searchParams.set("id", RESPONSE_ID);',
            '    chatbotUrl.searchParams.set("launch_nonce", launchNonce);',
            '    chatbotUrl.searchParams.set("return_url", returnUrl);',
            '    chatbotUrl.searchParams.set("language", "english");',
            '    chatbotUrl.searchParams.set("survey_claim", selected.survey_claim);',
            '    chatbotUrl.searchParams.set("survey_claim_initial_credence", String(selected.survey_claim_initial_credence));',
            "    if (CONTROL_FLAG) {",
            '      chatbotUrl.searchParams.set("control_flag", CONTROL_FLAG);',
            "    }",
            "    if (CONTROL_CLAIM) {",
            '      chatbotUrl.searchParams.set("control_claim", CONTROL_CLAIM);',
            "    }",
            "",
            "    if (PROLIFIC_PID) {",
            '      chatbotUrl.searchParams.set("prolific_pid", PROLIFIC_PID);',
            "    }",
            "    if (STUDY_ID) {",
            '      chatbotUrl.searchParams.set("study_id", STUDY_ID);',
            "    }",
            "    if (SESSION_ID) {",
            '      chatbotUrl.searchParams.set("session_id", SESSION_ID);',
            "    }",
            "    return chatbotUrl.toString();",
            "  }",
            "",
            '  if (readQueryParam("chat_return") === "1") {',
            '    writeEmbedded("discussion_claim", readQueryParam("discussion_claim"));',
            '    writeEmbedded("discussion_claim_initial_credence", readQueryParam("discussion_claim_initial_credence"));',
            '    writeEmbedded("discussion_claim_final_credence", readQueryParam("discussion_claim_final_credence"));',
            "    window.setTimeout(clickNext, 400);",
            "    return;",
            "  }",
            "",
            "  var eligibleClaims = buildEligibleClaims();",
            "  if (!eligibleClaims.length) {",
            '    writeEmbedded("survey_claim", "");',
            '    writeEmbedded("survey_claim_initial_credence", "");',
            '    writeEmbedded("survey_claim_source_qid", "");',
            '    writeEmbedded("chatbot_url", "");',
            '    writeEmbedded("discussion_claim", "");',
            '    writeEmbedded("discussion_claim_initial_credence", "");',
            '    writeEmbedded("discussion_claim_final_credence", "");',
            "    window.setTimeout(clickNext, 400);",
            "    return;",
            "  }",
            "",
            "  var selected = eligibleClaims[Math.floor(Math.random() * eligibleClaims.length)];",
            "  var chatbotUrl = buildChatbotUrl(selected, buildReturnUrl());",
            '  writeEmbedded("survey_claim", selected.survey_claim);',
            '  writeEmbedded("survey_claim_initial_credence", String(selected.survey_claim_initial_credence));',
            '  writeEmbedded("survey_claim_source_qid", selected.survey_claim_source_qid);',
            '  writeEmbedded("chatbot_url", chatbotUrl);',
            '  writeEmbedded("discussion_claim", "");',
            '  writeEmbedded("discussion_claim_initial_credence", "");',
            '  writeEmbedded("discussion_claim_final_credence", "");',
            "  window.location.replace(chatbotUrl);",
            "});",
        ]
    )


def make_chatbot_redirect_question(qsf: dict[str, Any], qid: str, chatbot_url: str, password: str) -> dict[str, Any]:
    survey_id = qsf.get("SurveyEntry", {}).get("SurveyID")
    question_text = (
        "We are preparing your StreetGPT follow-up. "
        "If you are not redirected automatically within a few seconds, please wait a moment and then use the next arrow."
    )
    return {
        "SurveyID": survey_id,
        "Element": "SQ",
        "PrimaryAttribute": qid,
        "SecondaryAttribute": question_text[:80],
        "TertiaryAttribute": None,
        "Payload": {
            "QuestionText": question_text,
            "DefaultChoices": False,
            "DataExportTag": "chatbotRedirect",
            "QuestionID": qid,
            "QuestionType": "DB",
            "Selector": "TB",
            "DataVisibility": {"Private": False, "Hidden": False},
            "Configuration": {"QuestionDescriptionOption": "UseText"},
            "QuestionDescription": question_text,
            "ChoiceOrder": [],
            "Validation": {"Settings": {"Type": "None"}},
            "GradingData": [],
            "Language": [],
            "NextChoiceId": 4,
            "NextAnswerId": 1,
            "QuestionJS": build_chatbot_question_js(chatbot_url, password),
        },
    }


def ensure_chatbot_redirect_question(
    qsf: dict[str, Any],
    *,
    chatbot_url: str,
    password: str,
    question_id: str = "QID399",
) -> None:
    chatbot_block = find_chatbot_block(qsf)
    chatbot_block["BlockElements"] = [{"Type": "Question", "QuestionID": question_id}]

    try:
        question = find_question(qsf, question_id)
    except ValueError:
        question = make_chatbot_redirect_question(qsf, question_id, chatbot_url, password)
        elements = qsf.setdefault("SurveyElements", [])
        insert_index = next(
            (index for index, element in enumerate(elements) if element.get("Element") == "STAT"),
            len(elements),
        )
        elements.insert(insert_index, question)
        return

    payload = question.setdefault("Payload", {})
    payload["QuestionText"] = (
        "We are preparing your StreetGPT follow-up. "
        "If you are not redirected automatically within a few seconds, please wait a moment and then use the next arrow."
    )
    payload["QuestionDescription"] = payload["QuestionText"]
    payload["DataExportTag"] = "chatbotRedirect"
    payload["QuestionType"] = "DB"
    payload["Selector"] = "TB"
    payload.setdefault("Configuration", {})["QuestionDescriptionOption"] = "UseText"
    payload.setdefault("Validation", {}).setdefault("Settings", {})["Type"] = "None"
    payload.setdefault("DataVisibility", {"Private": False, "Hidden": False})
    payload["QuestionJS"] = build_chatbot_question_js(chatbot_url, password)


def prepare_qsf(
    qsf_path: Path,
    output_path: Path,
    chatbot_url: str,
    password: str,
    codes: dict[str, str],
) -> dict[str, Any]:
    qsf = json.loads(qsf_path.read_text(encoding="utf-8"))
    survey_flow = find_survey_flow(qsf)
    ensure_embedded_data_fields(
        survey_flow,
        [
            make_embedded_data_field("PROLIFIC_PID"),
            make_embedded_data_field("STUDY_ID"),
            make_embedded_data_field("SESSION_ID"),
            make_embedded_data_field("control_flag"),
            make_embedded_data_field("control_claim"),
            make_embedded_data_field("chatbot_url"),
            make_embedded_data_field("survey_claim"),
            make_embedded_data_field("survey_claim_initial_credence", "Number"),
            make_embedded_data_field("survey_claim_source_qid"),
            make_embedded_data_field("discussion_claim"),
            make_embedded_data_field("discussion_claim_initial_credence", "Number"),
            make_embedded_data_field("discussion_claim_final_credence", "Number"),
        ],
    )
    patch_prolific_redirects(qsf, codes)
    ensure_chatbot_redirect_question(
        qsf,
        chatbot_url=chatbot_url,
        password=password,
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
        default="election_conspiracy_experiment_files/2025_American_Survey_original.qsf",
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
