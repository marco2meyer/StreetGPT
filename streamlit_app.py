import html
import json
import os
import random
import re
import string
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytz
import streamlit as st
import streamlit.components.v1 as components
import tiktoken
import yaml
from openai import OpenAI
from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError
from tenacity import RetryError, retry, stop_after_attempt, wait_random_exponential

### Setup ##

def get_secret(name: str, default=None):
    # Read only from environment to avoid requiring a secrets.toml
    env_val = os.getenv(name)
    return env_val if (env_val is not None and env_val != "") else default


def get_query_param(url_params: dict[str, list[str]], name: str, default=""):
    value = url_params.get(name, [default])
    if not value:
        return default
    return value[0]


def parse_int_param(value, default=0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def normalize_claim(value):
    if value is None:
        return 0
    claim = str(value).strip()
    return claim if claim else 0


def normalize_language(value) -> str:
    language = str(value or "english").strip().lower()
    return language if language in {"english", "german"} else "english"


def parse_bool_param(value, default=False) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "y", "on", "control"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "treatment"}:
        return False
    return default


def read_query_context():
    url_params = st.experimental_get_query_params()
    legacy_claim = normalize_claim(get_query_param(url_params, "claim", ""))
    legacy_credence = parse_int_param(get_query_param(url_params, "credence", 0), 0)
    survey_claim = normalize_claim(
        get_query_param(
            url_params,
            "survey_claim",
            get_query_param(url_params, "evaluation_claim", legacy_claim),
        )
    )
    survey_claim_initial_credence = parse_int_param(
        get_query_param(
            url_params,
            "survey_claim_initial_credence",
            get_query_param(
                url_params,
                "survey_credence",
                get_query_param(url_params, "evaluation_credence", legacy_credence),
            ),
        ),
        0,
    )
    control_flag = parse_bool_param(
        get_query_param(url_params, "control_flag", get_query_param(url_params, "control", "0")),
        False,
    )
    control_claim = normalize_claim(
        get_query_param(url_params, "control_claim", get_query_param(url_params, "control_claim_text", "")),
    )
    discussion_claim_override = normalize_claim(
        get_query_param(url_params, "discussion_claim_seed", get_query_param(url_params, "discussion_claim", "")),
    )
    if discussion_claim_override not in (None, 0, "0"):
        discussion_claim_seed = discussion_claim_override
    else:
        discussion_claim_seed = survey_claim

    return {
        "password": get_query_param(url_params, "password", "na"),
        "survey_claim": survey_claim,
        "survey_claim_initial_credence": survey_claim_initial_credence,
        "control_flag": control_flag,
        "control_claim": control_claim,
        "discussion_claim_seed": discussion_claim_seed,
        "launch_nonce": str(get_query_param(url_params, "launch_nonce", "")).strip(),
        "id": str(get_query_param(url_params, "id", "")).strip(),
        "language": normalize_language(get_query_param(url_params, "language", "english")),
        "prolific_pid": str(get_query_param(url_params, "prolific_pid", "")).strip(),
        "study_id": str(get_query_param(url_params, "study_id", "")).strip(),
        "session_id": str(get_query_param(url_params, "session_id", "")).strip(),
        "return_url": str(get_query_param(url_params, "return_url", "")).strip(),
    }

# ---- Helper utilities (must be defined before first use) ----
def generate_random_id(length=10):
    letters = string.ascii_letters + string.digits
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str

def get_current_time_in_berlin():
    berlin_tz = pytz.timezone('Europe/Berlin')
    current_time = datetime.now(berlin_tz)
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S %Z%z")
    return formatted_time

def num_tokens_from_prompt(prompt, encoding_name="cl100k_base") -> int:
    """Returns the number of tokens in a text string."""
    string_buf = ""
    for dic in prompt:
        content = dic.get("content")
        string_buf += f"{content}\n"
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string_buf))
    return num_tokens


def should_end_chat(response: str) -> bool:
    lowered = response.lower()
    return "goodbye" in lowered or "return to the survey" in lowered


def render_return_handoff(return_url: str):
    if not return_url:
        return

    safe_return_url = html.escape(return_url, quote=True)
    st.markdown(
        (
            '<div style="margin-top: 1rem;">'
            f'<a href="{safe_return_url}" target="_self" '
            'style="display:inline-block;padding:0.6rem 1rem;'
            'border-radius:0.5rem;border:1px solid #d0d7de;'
            'text-decoration:none;font-weight:600;">Return to the survey</a>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )
    st.caption("You will be returned automatically in a few seconds if nothing happens.")
    components.html(
        f"""
        <script>
        window.setTimeout(function() {{
          window.top.location.href = {json.dumps(return_url)};
        }}, 4000);
        </script>
        """,
        height=0,
    )


def truncate_text(value: str, limit: int = 500) -> str:
    collapsed = re.sub(r"\s+", " ", str(value or "")).strip()
    return collapsed[:limit]


def normalize_credence(value, default=None):
    parsed = parse_int_param(value, 0)
    if 1 <= parsed <= 10:
        return parsed
    return default


def extract_json_object(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in extractor response")
    return json.loads(text[start:end + 1])


def compose_chat_outcome(discussion_claim: str, initial_credence, final_credence) -> dict:
    return {
        "discussion_claim": discussion_claim,
        "discussion_claim_initial_credence": initial_credence,
        "discussion_claim_final_credence": final_credence,
    }


def normalize_chat_outcome(raw_outcome: dict, seeded_discussion_claim) -> dict:
    seeded_claim_text = ""
    if seeded_discussion_claim not in (None, 0, "0"):
        seeded_claim_text = truncate_text(seeded_discussion_claim)

    discussion_claim = truncate_text(
        raw_outcome.get("discussion_claim")
        or raw_outcome.get("discussion_claim_text")
        or raw_outcome.get("revised_claim")
        or raw_outcome.get("revised_claim_text")
        or raw_outcome.get("clarified_claim")
        or seeded_claim_text
    )
    initial_credence = normalize_credence(
        raw_outcome.get("discussion_claim_initial_credence")
        or raw_outcome.get("revised_claim_initial_credence")
        or raw_outcome.get("clarified_claim_initial_confidence"),
        default=None,
    )
    final_credence = normalize_credence(
        raw_outcome.get("discussion_claim_final_credence")
        or raw_outcome.get("revised_claim_final_credence")
        or raw_outcome.get("clarified_claim_final_confidence"),
        default=None,
    )
    return compose_chat_outcome(discussion_claim, initial_credence, final_credence)


def build_chat_outcome(
    messages,
    seeded_discussion_claim,
    survey_claim="",
    control_flag=False,
    control_claim="",
):
    transcript_lines = []
    for message in messages:
        content = str(message.get("content", "")).strip()
        role = str(message.get("role", "")).strip().lower()
        if content and role in {"assistant", "user"}:
            transcript_lines.append(f"{role.upper()}: {content}")
    transcript = "\n\n".join(transcript_lines)

    fallback = normalize_chat_outcome({}, seeded_discussion_claim)
    fallback["extractor_status"] = "fallback"
    fallback["extractor_model"] = ""

    if not transcript:
        fallback["extractor_error"] = "empty_transcript"
        return fallback

    extraction_system = (
        "You extract structured study outcomes from a finished Street Epistemology chat. "
        "Return JSON only with keys discussion_claim, discussion_claim_initial_credence, and discussion_claim_final_credence. "
        "discussion_claim should be the clarified or rephrased version of the SURVEY CLAIM that the participant settled on near the start of the chat. "
        "discussion_claim_initial_credence should be the 1-10 confidence they gave for that clarified survey claim near the start of the chat, after clarification. "
        "discussion_claim_final_credence should be the 1-10 confidence they gave at the end for that same clarified survey claim. "
        "If this is a control-condition transcript, the middle of the conversation may discuss a separate control claim. Ignore that and still extract only the clarified survey claim and its baseline/endline confidence. "
        "Use null for missing values. Do not infer a final credence unless the participant explicitly gives one."
    )
    seeded_claim_text = "" if seeded_discussion_claim in (None, 0, "0") else str(seeded_discussion_claim)
    survey_claim_text = "" if survey_claim in (None, 0, "0") else str(survey_claim)
    control_claim_text = "" if control_claim in (None, 0, "0") else str(control_claim)
    extraction_user = (
        f"Condition: {'control' if control_flag else 'treatment'}\n"
        f"Survey claim measured in Qualtrics outside the chatbot: {survey_claim_text or 'null'}\n"
        f"Seeded discussion claim for the chatbot: {seeded_claim_text or 'null'}\n\n"
        f"Separate control-claim discussion topic, if any: {control_claim_text or 'null'}\n\n"
        f"Transcript:\n{transcript}"
    )
    model = st.session_state.get("openai_model", get_secret("OPENAI_MODEL", "gpt-5"))

    try:
        request_kwargs = {
            "model": model,
            "input": [
                {"role": "system", "content": extraction_system},
                {"role": "user", "content": extraction_user},
            ],
        }
        if str(model).lower().startswith("gpt-5"):
            request_kwargs["reasoning"] = {"effort": "low"}
        response = client.responses.create(**request_kwargs)
        parsed = extract_json_object(response.output_text or "")
        outcome = normalize_chat_outcome(parsed, seeded_discussion_claim)
        outcome["extractor_status"] = "ok"
        outcome["extractor_model"] = model
        return outcome
    except Exception as e:
        st.session_state["error_messages"] += f"chat_outcome_extract_error: {type(e).__name__}: {e}\n"
        fallback["extractor_error"] = f"{type(e).__name__}: {e}"
        fallback["extractor_model"] = model
        return fallback


def append_chat_outcome_to_return_url(return_url: str, chat_outcome: dict) -> str:
    if not return_url:
        return return_url

    split_url = urlsplit(return_url)
    params = dict(parse_qsl(split_url.query, keep_blank_values=True))
    for legacy_field_name in (
        "revised_claim",
        "revised_claim_text",
        "revised_claim_initial_credence",
        "revised_claim_final_credence",
    ):
        params.pop(legacy_field_name, None)
    for field_name in (
        "discussion_claim",
        "discussion_claim_initial_credence",
        "discussion_claim_final_credence",
    ):
        value = chat_outcome.get(field_name)
        if value in (None, ""):
            params.pop(field_name, None)
        else:
            params[field_name] = str(value)
    return urlunsplit(
        (
            split_url.scheme,
            split_url.netloc,
            split_url.path,
            urlencode(params, doseq=True),
            split_url.fragment,
        )
    )

query_context = read_query_context()
st.session_state["password"] = query_context["password"]

# Centralized password: single PASSWORD from env or secrets
password_secret = get_secret("PASSWORD", "")
allowed_passwords = {password_secret} if password_secret else set()

st.session_state["password_correct"] = (
    st.session_state["password"] in allowed_passwords if allowed_passwords else False
)

if st.session_state["password_correct"] == False:
    st.write("Wrong password in URL parameter 'password'")
    st.stop()

# Setup MongoDB
@st.cache_resource
def get_mongo_client(uri: str):
    return MongoClient(uri)

@st.cache_resource
def get_mongo_db(_client: MongoClient, db_name: str):
    return _client[db_name]

MONGO_URI = get_secret("MONGO_URI")
MONGO_DB_NAME = get_secret("MONGO_DB_NAME", "streetgpt")
mongo_client = get_mongo_client(MONGO_URI)
mongo_db = get_mongo_db(mongo_client, MONGO_DB_NAME)
conversations_col = mongo_db["conversations"]

# Ensure indexes (idempotent)
try:
    conversations_col.create_index([("session_id", ASCENDING)], unique=True)
    conversations_col.create_index([("created_at", ASCENDING)])
    conversations_col.create_index([("app", ASCENDING)])
except Exception:
    pass


APP_NAME = get_secret("APP_NAME", "streetgpt")

# Load system messages from YAML config
def load_system_messages():
    # Default path inside container, fallback to local dev path
    default_path = "/app/config/system_messages.yaml"
    path = get_secret("SYSTEM_MESSAGES_FILE", default_path)
    if not os.path.isfile(path):
        # local fallback for non-docker runs
        local_fallback = os.path.join(os.path.dirname(__file__), "config", "system_messages.yaml")
        if os.path.isfile(local_fallback):
            path = local_fallback
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        st.error(f"Failed to load system messages from {path}: {e}")
        return {}

SYSTEM_MESSAGES = load_system_messages()

def get_system_message(
    survey_claim: str | int,
    survey_claim_initial_credence: int,
    discussion_claim_seed: str | int,
    control_claim: str | int,
    control_flag: bool,
    language: str,
):
    is_claim = 0 if discussion_claim_seed == 0 else 1
    lang_key = "german" if language == "german" else "english"
    if is_claim:
        template_key = "with_claim_control" if control_flag else "with_claim"
        template = ((SYSTEM_MESSAGES.get(template_key, {}) or {}).get(lang_key))
        if not template:
            template = ((SYSTEM_MESSAGES.get("with_claim", {}) or {}).get(lang_key))
        if not template:
            template = "You are StreetGPT. Keep answers concise. Claim: {claim}."
        try:
            return template.format(
                claim=discussion_claim_seed,
                credence=survey_claim_initial_credence,
                survey_claim=survey_claim,
                survey_credence=survey_claim_initial_credence,
                survey_claim_initial_credence=survey_claim_initial_credence,
                discussion_claim=discussion_claim_seed,
                control_claim=control_claim,
            )
        except Exception:
            return template
    else:
        message = (
            (SYSTEM_MESSAGES.get("no_claim", {}) or {}).get(lang_key)
        )
        if not message:
            message = "You are StreetGPT. Keep answers concise."
        return message

# ---- OpenAI client and chat helpers (defined before UI logic) ----
client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))  # Initialize OpenAI client once

def handle_chat_completion(client, model, messages, minimal_reasoning=True):
    full_response = ""
    message_placeholder = st.empty()
    try:
        # Prefer Responses API for GPT‑5 (supports reasoning controls)
        if str(model).lower().startswith("gpt-5"):
            kwargs = {"model": model, "messages": messages}
            if minimal_reasoning:
                kwargs["reasoning"] = {"effort": "low"}
            try:
                with client.responses.stream(**kwargs) as stream:
                    for event in stream:
                        # event.delta can be a string or missing; guard accordingly
                        if getattr(event, "type", "").startswith("response.output_text"):
                            delta = getattr(event, "delta", "") or ""
                            if delta:
                                full_response += str(delta)
                                message_placeholder.markdown(full_response + "▌")
                                st.session_state["completion_tokens"] += 1
                    _ = stream.get_final_response()
                return full_response
            except Exception as e_resp:
                # Fall through to Chat Completions on any Responses error
                st.session_state["error_messages"] += f"responses_api_error: {type(e_resp).__name__}: {e_resp}\n"

        # Fallback: Chat Completions streaming (works across many models)
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            # delta may be an object (with .content) or a dict; guard both
            delta_obj = getattr(chunk.choices[0], "delta", None)
            delta = ""
            if isinstance(delta_obj, dict):
                delta = delta_obj.get("content", "")
            else:
                delta = getattr(delta_obj, "content", "") or ""
            if delta:
                full_response += delta
                message_placeholder.markdown(full_response + "▌")
                st.session_state["completion_tokens"] += 1
        return full_response
    except Exception as e2:
        st.session_state["error_messages"] += f"from handle (chat streaming failed): {type(e2).__name__}: {e2}\n"
        raise e2

@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(min=2, max=5)
)
def chat_completion_with_backoff(messages):
    model = st.session_state.get("openai_model", get_secret("OPENAI_MODEL", "gpt-5"))
    full_response = handle_chat_completion(client=client, model=model, messages=messages, minimal_reasoning=True)
    return full_response

if "openai_model" not in st.session_state:
    # Model comes from env var OPENAI_MODEL; default to gpt-5 if unset.
    st.session_state["openai_model"] = get_secret("OPENAI_MODEL", "gpt-5")


launch_signature = json.dumps(
    {
        "launch_nonce": query_context["launch_nonce"],
        "id": query_context["id"],
        "survey_claim": query_context["survey_claim"],
        "survey_claim_initial_credence": query_context["survey_claim_initial_credence"],
        "control_flag": query_context["control_flag"],
        "control_claim": query_context["control_claim"],
        "language": query_context["language"],
        "prolific_pid": query_context["prolific_pid"],
        "study_id": query_context["study_id"],
        "session_id": query_context["session_id"],
        "return_url": query_context["return_url"],
    },
    sort_keys=True,
)

if st.session_state.get("launch_signature") != launch_signature:
    st.session_state["launch_signature"] = launch_signature
    st.session_state["error_messages"] = ""
    st.session_state["last_model"] = ""

    st.session_state["survey_claim"] = query_context["survey_claim"]
    st.session_state["survey_claim_initial_credence"] = query_context["survey_claim_initial_credence"]
    st.session_state["control_flag"] = query_context["control_flag"]
    st.session_state["control_claim"] = query_context["control_claim"]
    st.session_state["discussion_claim_seed"] = query_context["discussion_claim_seed"]
    st.session_state["discussion_claim"] = ""
    st.session_state["discussion_claim_initial_credence"] = None
    st.session_state["discussion_claim_final_credence"] = None
    st.session_state["id"] = query_context["id"]
    st.session_state["language"] = query_context["language"]
    st.session_state["prolific_pid"] = query_context["prolific_pid"]
    st.session_state["study_id"] = query_context["study_id"]
    st.session_state["session_id"] = query_context["session_id"]
    st.session_state["return_url_base"] = query_context["return_url"]
    st.session_state["return_url"] = query_context["return_url"]
    st.session_state["chat_outcome"] = {}

    # If no id is passed, generate random id and write to db
    if not st.session_state["id"]:
        st.session_state["id"] = generate_random_id()

    # Initialize variables for completion tokens and prompt tokens
    st.session_state["completion_tokens"] = 0
    st.session_state["prompt_tokens"] = 0

    # Set show user text input to True
    st.session_state["input_active"] = 1
    st.session_state["messages"] = []

    # Create conversation document (upsert by session_id)
    current_time = get_current_time_in_berlin()
    try:
        conversations_col.update_one(
            {"session_id": st.session_state["id"]},
            {"$setOnInsert": {
                "session_id": st.session_state["id"],
                "app": APP_NAME,
                "created_at": current_time,
                "updated_at": current_time,
                "survey_claim": st.session_state["survey_claim"],
                "survey_claim_initial_credence": st.session_state["survey_claim_initial_credence"],
                "control_flag": st.session_state["control_flag"],
                "control_claim": st.session_state["control_claim"],
                "discussion_claim": st.session_state["discussion_claim"],
                "discussion_claim_initial_credence": st.session_state["discussion_claim_initial_credence"],
                "discussion_claim_final_credence": st.session_state["discussion_claim_final_credence"],
                "prolific_pid": st.session_state["prolific_pid"],
                "study_id": st.session_state["study_id"],
                "prolific_session_id": st.session_state["session_id"],
                "return_url_base": st.session_state["return_url_base"],
                "return_url": st.session_state["return_url"],
                "chat_outcome": st.session_state["chat_outcome"],
                "password_used": st.session_state["password"],
                "last_model": "",
                "error_messages": "",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "messages": []
            }},
            upsert=True
        )
    except PyMongoError as e:
        st.error(f"Failed to initialize conversation in MongoDB: {e}")
        st.stop()
    
    
opening_message_english = "Hi there! I'm Chip. I'm here to help you explore and reflect on your beliefs. Before we start: this is a conversation about how we know things. Some questions can feel probing; you can skip any or stop anytime. Okay to proceed?"
opening_message_german = "Hallo, mein Name ist Chip. Ich kann dir helfen, deine Überzeugungen zu hinterfragen. Bevor wir beginnen: Dies ist ein Gespräch darüber, woher ir Dinge wissen. Du kannst jederzeit eine Frage überspringen oder ganz aufhören. Einverstanden, dass wir fortfahren?"
   
if st.session_state["discussion_claim_seed"] == 0:
    # No initial claim provided
    if st.session_state["language"] == 'german':
        opening_message = opening_message_german
    else:
        opening_message = opening_message_english
else:
    # Claim provided
    if st.session_state["language"] == 'german':
        opening_message = opening_message_german
    else:
        opening_message = opening_message_english

# Determine system message from YAML config
system_message = get_system_message(
    survey_claim=st.session_state["survey_claim"],
    survey_claim_initial_credence=st.session_state["survey_claim_initial_credence"],
    discussion_claim_seed=st.session_state["discussion_claim_seed"],
    control_claim=st.session_state["control_claim"],
    control_flag=st.session_state["control_flag"],
    language=st.session_state["language"],
)

# Persist selected system_message once per conversation
try:
    conversations_col.update_one(
        {"session_id": st.session_state["id"]},
        {"$set": {
            "system_message": system_message,
            "survey_claim": st.session_state["survey_claim"],
            "survey_claim_initial_credence": st.session_state["survey_claim_initial_credence"],
            "control_flag": st.session_state["control_flag"],
            "control_claim": st.session_state["control_claim"],
            "discussion_claim": st.session_state.get("discussion_claim", ""),
            "discussion_claim_initial_credence": st.session_state.get("discussion_claim_initial_credence"),
            "discussion_claim_final_credence": st.session_state.get("discussion_claim_final_credence"),
            "prolific_pid": st.session_state.get("prolific_pid", ""),
            "study_id": st.session_state.get("study_id", ""),
            "prolific_session_id": st.session_state.get("session_id", ""),
            "return_url_base": st.session_state.get("return_url_base", ""),
            "return_url": st.session_state.get("return_url", ""),
            "chat_outcome": st.session_state.get("chat_outcome", {}),
            "password_used": st.session_state["password"],
        }},
        upsert=False,
    )
except PyMongoError as e:
    st.session_state["error_messages"] += f"Mongo update system_message error: {e}\n"

### Main App ##

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({"role": "assistant", "content": opening_message, "avatar": "🧑‍🎤"})

# Show chat messages in streamlit
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=message["avatar"]):
        st.markdown(message["content"])

# allow users to send messages and process them 
if st.session_state["input_active"] == 1:
  
    if prompt := st.chat_input("Write a message", key="input"):
        st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "🧐"})
        with st.chat_message("user", avatar="🧐"):
            st.markdown(prompt)
        
        # Create promt to OpenAI
        with st.chat_message("assistant", avatar="🧑‍🎤"):
            
            # Create a list to store the complete prompt sent to OpenAI
            complete_prompt = [{"role": "system", "content": system_message}] + \
                            [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
        
            # Send the prompt to OpenAI, and get a response  
            try:
                st.session_state["last_model"] = st.session_state.get("openai_model", get_secret("OPENAI_MODEL", "gpt-5"))
                full_response = chat_completion_with_backoff(messages=complete_prompt)
            except RetryError:
                # If retries exhausted, surface the error
                raise
            
            # Update session state with new response
            st.session_state.messages.append({"role": "assistant", "content": full_response, "avatar": "🧑‍🎤"})

            # Update vars for counting tokens
            # Estimating tokens for the prompt
            prompt_tokens = num_tokens_from_prompt(complete_prompt)
            st.session_state["prompt_tokens"] += prompt_tokens
            
            # Stop the chat once the handoff message is given.
            if should_end_chat(full_response):
                chat_outcome = build_chat_outcome(
                    messages=st.session_state.messages,
                    seeded_discussion_claim=st.session_state.get("discussion_claim_seed", ""),
                    survey_claim=st.session_state.get("survey_claim", ""),
                    control_flag=st.session_state.get("control_flag", False),
                    control_claim=st.session_state.get("control_claim", ""),
                )
                st.session_state["chat_outcome"] = chat_outcome
                st.session_state["discussion_claim"] = chat_outcome.get("discussion_claim", "")
                st.session_state["discussion_claim_initial_credence"] = chat_outcome.get("discussion_claim_initial_credence")
                st.session_state["discussion_claim_final_credence"] = chat_outcome.get("discussion_claim_final_credence")
                st.session_state["return_url"] = append_chat_outcome_to_return_url(
                    st.session_state.get("return_url_base", st.session_state.get("return_url", "")),
                    chat_outcome,
                )
                st.session_state["input_active"] = 0

            
            # Persist conversation to MongoDB
            try:
                # Append the latest user and assistant messages only (not the system message)
                messages_to_append = [
                    {"role": "user", "content": prompt, "ts": get_current_time_in_berlin()},
                    {"role": "assistant", "content": full_response, "ts": get_current_time_in_berlin()},
                ]
                conversations_col.update_one(
                    {"session_id": st.session_state["id"]},
                    {
                        "$set": {
                            "updated_at": get_current_time_in_berlin(),
                            "last_model": st.session_state["last_model"],
                            "error_messages": st.session_state["error_messages"],
                            "prompt_tokens": st.session_state["prompt_tokens"],
                            "completion_tokens": st.session_state["completion_tokens"],
                            "password_used": st.session_state["password"],
                            "survey_claim": st.session_state.get("survey_claim", ""),
                            "survey_claim_initial_credence": st.session_state.get("survey_claim_initial_credence", 0),
                            "control_flag": st.session_state.get("control_flag", False),
                            "control_claim": st.session_state.get("control_claim", ""),
                            "discussion_claim": st.session_state.get("discussion_claim", ""),
                            "discussion_claim_initial_credence": st.session_state.get("discussion_claim_initial_credence"),
                            "discussion_claim_final_credence": st.session_state.get("discussion_claim_final_credence"),
                            "prolific_pid": st.session_state.get("prolific_pid", ""),
                            "study_id": st.session_state.get("study_id", ""),
                            "prolific_session_id": st.session_state.get("session_id", ""),
                            "return_url_base": st.session_state.get("return_url_base", ""),
                            "return_url": st.session_state.get("return_url", ""),
                            "chat_outcome": st.session_state.get("chat_outcome", {}),
                            "system_message": system_message,
                        },
                        "$push": {"messages": {"$each": messages_to_append}}
                    },
                    upsert=True
                )
            except PyMongoError as e:
                st.session_state["error_messages"] += f"Mongo persist error: {e}\n"

else:
    st.chat_input("Write a message", key="input", disabled=True)
    if "input" in st.session_state:
        del st.session_state["input"]
    render_return_handoff(st.session_state.get("return_url", ""))

# To generate random IDs
def generate_random_id(length=10):
    letters = string.ascii_letters + string.digits
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str

# To return current time in Berlin
def get_current_time_in_berlin():
    berlin_tz = pytz.timezone('Europe/Berlin')
    current_time = datetime.now(berlin_tz)
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S %Z%z")
    return formatted_time

# Count number of prompt tokens
def num_tokens_from_prompt(prompt, encoding_name="cl100k_base") -> int:
    """Returns the number of tokens in a text string."""
    string = ""
    for dic in prompt:
        content = dic.get("content")
        string += f"{content}\n"
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

# (moved chat helpers above)

def write_to_db(db, row_number, column, value):
    db.update_cell(row_number, column, value)
   
def read_from_db(db, row, column):
    return db.cell(row, column).value
