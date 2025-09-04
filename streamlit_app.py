import tiktoken
import streamlit as st
import random
import string
from datetime import datetime
import pytz
from tenacity import retry, wait_random_exponential, stop_after_attempt, RetryError
from openai import OpenAI
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError
import os
import yaml

### Setup ##

def get_secret(name: str, default=None):
    # Read only from environment to avoid requiring a secrets.toml
    env_val = os.getenv(name)
    return env_val if (env_val is not None and env_val != "") else default

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

url_params = st.experimental_get_query_params()
st.session_state["password"] = url_params.get('password', ["na"])[0]

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

def get_system_message(claim: str | int, credence: int, language: str):
    is_claim = 0 if claim == 0 else 1
    lang_key = "german" if language == "german" else "english"
    if is_claim:
        template = (
            (SYSTEM_MESSAGES.get("with_claim", {}) or {}).get(lang_key)
        )
        if not template:
            template = "You are StreetGPT. Keep answers concise. Claim: {claim}."
        try:
            return template.format(claim=claim, credence=credence)
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
    
    st.session_state["error_messages"] = ""
    st.session_state["last_model"] = ""
    
    #Extract URL params
    url_params = st.experimental_get_query_params()
    st.session_state["credence"] = int(url_params.get('credence', [0])[0])
    st.session_state["claim"] = url_params.get('claim', [0])[0]
    st.session_state["id"] = url_params.get('id', [0])[0]
    st.session_state["language"] = url_params.get('language', ['english'])[0]
    
    # If no id is passed, generate random id and write to db
    if st.session_state["id"] == 0:
        st.session_state["id"] = generate_random_id()
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
                "claim": st.session_state["claim"],
                "credence": st.session_state["credence"],
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
        
    # Initialize variables for completion tokens and prompt tokens
    st.session_state["completion_tokens"] = 0
    st.session_state["prompt_tokens"] = 0
    
    # Set show user text input to True
    st.session_state["input_active"] = 1
    
    
opening_message_english = "Hi there! I'm Chip. I'm here to help you explore and reflect on your beliefs. Before we start: this is a conversation about how we know things. Some questions can feel probing; you can skip any or stop anytime. Okay to proceed?"
opening_message_german = "Hallo, mein Name ist Chip. Ich kann dir helfen, deine Überzeugungen zu hinterfragen. Bevor wir beginnen: Dies ist ein Gespräch darüber, woher ir Dinge wissen. Du kannst jederzeit eine Frage überspringen oder ganz aufhören. Einverstanden, dass wir fortfahren?"
   
if st.session_state["claim"] == 0:
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
    claim=st.session_state["claim"],
    credence=st.session_state["credence"],
    language=st.session_state["language"],
)

# Persist selected system_message once per conversation
try:
    conversations_col.update_one(
        {"session_id": st.session_state["id"]},
        {"$set": {"system_message": system_message}},
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
            
            # If the chatbot uses the word goodbye, disable the input field.
            if "goodbye" in full_response.lower():
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
    del st.session_state["input"]

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
