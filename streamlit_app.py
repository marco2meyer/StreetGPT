import openai
import tiktoken
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random
import string
from datetime import datetime
import pytz
from tenacity import retry, wait_random_exponential, stop_after_attempt, RetryError



@st.cache_resource
def get_db_conn(credentials_path, scope):
    credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
    gc = gspread.authorize(credentials)
    return gc

@st.cache_resource
def get_db_sheet(_gc, spreadsheet_id, sheet):
    return _gc.open_by_key(spreadsheet_id).get_worksheet(sheet)

def write_to_db(db, row_number, column, value):
    db.update_cell(row_number, column, value)
   
def read_from_db(db, row, column):
    return db.cell(row, column).value

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

# Function to query Open-AI
@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(min=2, max=5)
)
def chat_completion_with_backoff(model, prompt):
    full_response = ""
    message_placeholder = st.empty()

    try:
        for response in openai.ChatCompletion.create(
                model=model,
                messages=prompt,
                stream=True
        ):
            full_response += response.choices[0].delta.get("content", "")
            message_placeholder.markdown(full_response + "▌")
            # Keep track of completion tokens
            st.session_state["completion_tokens"] += 1

        return full_response
    except Exception as e:
        st.session_state["error_messages"] += str(e) + "\n"
        raise e


### Setup ##

url_params = st.experimental_get_query_params()
st.session_state["password"] = url_params.get('password', ["na"])[0]
if st.session_state["password"] in st.secrets["PASSWORD"]:
    st.session_state["password_correct"] = True
else:
    st.session_state["password_correct"] = False

if st.session_state["password_correct"] == False:
    st.write("Wrong password in URL parameter 'password'")
    st.stop()

# Setup GSheet doc
scope = ['https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive']

gc = get_db_conn('gsheetscreds.json', scope)
spreadsheet_id = st.secrets["GSHEET_ID"]
db = get_db_sheet(gc, spreadsheet_id, 0)
system_messages_db = get_db_sheet(gc, spreadsheet_id, 1)


# The columns of the db
id_column = 1
start_time_column = 2
end_time_column = 3
claim_column = 4
credence_column = 5
name_column = 6
conversation_column = 7
completion_tokens_column = 8
prompt_tokens_column = 9
password_column = 10
error_column = 11

if "openai_model" not in st.session_state:
    st.session_state["openai_model"] = "gpt-4"
    st.session_state["openai_backup_model"] = "gpt-3.5-turbo-16k"
    st.session_state["error_messages"] = ""
    
    #Extract URL params
    url_params = st.experimental_get_query_params()
    st.session_state["credence"] = int(url_params.get('credence', [0])[0])
    st.session_state["claim"] = url_params.get('claim', [0])[0]
    st.session_state["id"] = url_params.get('id', [0])[0]

    
    # If no id is passed, generate random id and write to db
    if st.session_state["id"] == 0:
        st.session_state["id"] = generate_random_id()
    
    # Make a new row in the database for this id
    db.append_row([st.session_state["id"]])

    # Determine db row for this conversation
    cell = db.find(st.session_state["id"], in_column=id_column) # Search for id in column A, the id column
    st.session_state["row_number"] = cell.row # Get the row number from the cell object
    
    # Write start time to db
    current_time = get_current_time_in_berlin()
    write_to_db(db, st.session_state["row_number"], start_time_column, current_time) # Set start time to current time in Berlin
    
    # Write claim and credence vars to db
    write_to_db(db, st.session_state["row_number"], claim_column, st.session_state["claim"])
    write_to_db(db, st.session_state["row_number"], credence_column, st.session_state["credence"])
        
    # Initialize variables for completion tokens and prompt tokens
    st.session_state["completion_tokens"] = 0
    st.session_state["prompt_tokens"] = 0
    
    # Set show user text input to True
    st.session_state["input_active"] = 1
    
    
if st.session_state["claim"] == 0:
    system_message_row = 2
    system_message_column = 2
    system_message = read_from_db(system_messages_db, system_message_row, system_message_column)
else:
    system_message_row = 3
    system_message_column = 2
    system_message = read_from_db(system_messages_db, system_message_row, system_message_column)
    #Make an f-string
    system_message = system_message.format(claim=st.session_state["claim"], credence=st.session_state["credence"])
    print(system_message)

opening_message = "Hi, my name is Diotima. I am a street epistemologist that can help you examine your beliefs. What is your name?"


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
    openai.api = st.secrets["OPENAI_API_KEY"]
    if prompt := st.chat_input("Write a message", key="input"):
        st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "🧐"})
        with st.chat_message("user", avatar="🧐"):
            st.markdown(prompt)
        
        # Create promt to OpenAI
        with st.chat_message("assistant", avatar="🧑‍🎤"):
            
            # Create a list to store the complete prompt sent to OpenAI
            complete_prompt = [{"role": "user", "content": system_message}] + \
                            [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
        
            # Send the prompt to OpenAI, and get a response    
            try:
                full_response = chat_completion_with_backoff(st.session_state["openai_model"], complete_prompt)
            except RetryError:
                full_response = chat_completion_with_backoff(st.session_state["openai_backup_model"], complete_prompt)
            
            # Update session state with new response
            st.session_state.messages.append({"role": "assistant", "content": full_response, "avatar": "🧑‍🎤"})

            # Update vars for counting tokens
            # Estimating tokens for the prompt
            prompt_tokens = num_tokens_from_prompt(complete_prompt)
            st.session_state["prompt_tokens"] += prompt_tokens
            
            # If the chatbot uses the word goodbye, disable the input field.
            if "goodbye" in full_response.lower():
                st.session_state["input_active"] = 0

            
            # Write the complete prompt and response to a file
            if len(st.session_state.messages) > 1:            
                # Combine all messages so far into an output string
                output_str = ""
                for message in complete_prompt[1:]:
                    output_str += f"{message['role']}: {message['content']}\n"
                output_str += f"assistant: {full_response}\n"
                # Write string to db
                write_to_db(db, st.session_state["row_number"], conversation_column, output_str)
                # Write name of respondent to db
                write_to_db(db, st.session_state["row_number"], name_column, st.session_state.messages[1]["content"])
                # Write number of completion tokens and prompt tokens to db
                write_to_db(db, st.session_state["row_number"], completion_tokens_column, st.session_state["completion_tokens"])
                write_to_db(db, st.session_state["row_number"], prompt_tokens_column, st.session_state["prompt_tokens"])
                
                #Write password to db
                write_to_db(db, st.session_state["row_number"], password_column, st.session_state["password"])

                #Write errors to db
                write_to_db(db, st.session_state["row_number"], error_column, st.session_state["error_messages"])


                # Write end_time to db
                current_time = get_current_time_in_berlin()
                write_to_db(db, st.session_state["row_number"], end_time_column, current_time) # Set start time to current time in Berlin

else:
    st.chat_input("Write a message", key="input", disabled=True)
    del st.session_state["input"]
