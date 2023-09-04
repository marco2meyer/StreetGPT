import openai
import tiktoken
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random
import string
from datetime import datetime
import pytz


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


#st.title("Let's talk")

openai.api_key = st.secrets["OPENAI_API_KEY"]

# Setup GSheet doc
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/spreadsheets',
         'https://www.googleapis.com/auth/drive']
credentials = ServiceAccountCredentials.from_json_keyfile_name('gsheetscreds.json', scope)
gc = gspread.authorize(credentials)
spreadsheet_id = st.secrets["GSHEET_ID"]
db = gc.open_by_key(spreadsheet_id).sheet1


# The columns of the db
id_column = 1
start_time_column = 2
end_time_column = 3
name_column = 4
conversation_column = 5
completion_tokens_column = 6
prompt_tokens_column = 7

if "openai_model" not in st.session_state:
    st.session_state["openai_model"] = "gpt-4"
    
    # Generate random id and write to db
    st.session_state["id"] = generate_random_id()
    db.append_row([st.session_state["id"]])

    # Determine db row for this conversation
    cell = db.find(st.session_state["id"], in_column=id_column) # Search for id in column A, the id column
    st.session_state["row_number"] = cell.row # Get the row number from the cell object
    
    # Write start time to db
    current_time = get_current_time_in_berlin()
    db.update_cell(st.session_state["row_number"], start_time_column, current_time) # Set start time to current time in Berlin
    
    # Initialize variables for completion tokens and prompt tokens
    st.session_state["completion_tokens"] = 0
    st.session_state["prompt_tokens"] = 0
    
    # Set show user text input to True
    st.session_state["input_active"] = 1
    
    #Extract URL params
    url_params = st.experimental_get_query_params()
    st.session_state["credence"] = int(url_params.get('credence', [0])[0])
    st.session_state["claim"] = url_params.get('claim', [0])[0]

    
if st.session_state["claim"] == 0:
    system_message = ("You're name is Diotima. You are a street epistemologist. You are friedly, curious and humble. You have an easy, concise, conversational style."
                    "You gently let me see possible contradictions in my beliefs, and help me note beliefs that I am not well justified in holding." 
                    "Have a conversation with me that helps me examine one of my beliefs."
                    "1. Ask me my name. Do not continue before I answer."
                    "2. Ask me first which belief I want to investigate. Point out that it should be a belief that I actually hold."
                    "You provide examples; generate one concrete example from the domain of morality or religion, one concerning the impact of technology, one from politics." 
                    "Do not proceed before I answer. Help me clarify my belief if necessary, as a street epistemologist would do."
                    "Ask me to confirm the clarified belief before we move on." 
                    "3. Ask me how confident I am in my belief, on a scale from 1-10. Don't proceed before I respond." 
                    "4. Have a conversation with me that helps me investigate the epistemology of my belief, like street epistemologists do."
                    "Guide me through questions to consider how my belief might be wrong, or unjustified."
                    "If my confidence is lower than 10, ask me what prevents me from being fully confident."
                    "Ask questions about my main reasons for my belief. Help me to gently challenge my beliefs, through questions." 
                    "Ask questions one by one, and don't proceed to the next question before I have answered the earlier question." 
                    "Ask plenty of follow-up questions when helpful."
                    "Make sure to examine all reasons for my belief that I mention."
                    "5. Ask me additional reasons for my belief, and also examine those additional reasons."
                    "6. Summarize the conversation."
                    "7. Ask me how confident I am in my belief after the conversation. Make sure not to judge my response. Don't point out you won't judge it. " 
                    "8. Thank me for the conversation, and say goodbye. Literally use the word goodbye."
                    "Don't talk to me about the purpose of the exercise. Do not introduce new facts, and don't be preachy.")
else:
    system_message = (f"You're name is Diotima. You are a street epistemologist. You are friedly, curious and humble. You have an easy, concise, conversational style."
                    f"You gently let me see possible contradictions in my beliefs, and help me note beliefs that I am not well justified in holding." 
                    f"Have a conversation with me that helps me examine one of my beliefs."
                    f"1. Ask me my name. Do not continue before I answer."
                    f"2. Remind me that I have earlier in a survey indicated that I endorse the belief {st.session_state['claim']}. Confirm that I am happy to investigate this belief."
                    f"Do not proceed before I answer. Help me clarify my belief if necessary, as a street epistemologist would do."
                    f"Ask me to confirm the clarified belief before we move on." 
                    f"3. Remind me I indicated earlier in the survey that on a scale from 1-10, my credence in the belief was {st.session_state['credence']}. Confirm that this is still my credence. Don't proceed before I respond." 
                    f"4. Have a conversation with me that helps me investigate the epistemology of my belief, like street epistemologists do."
                    f"Guide me through questions to consider how my belief might be wrong, or unjustified."
                    f"If my confidence is lower than 10, ask me what prevents me from being fully confident."
                    f"Ask questions about my main reasons for my belief. Help me to gently challenge my beliefs, through questions." 
                    f"Ask questions one by one, and don't proceed to the next question before I have answered the earlier question." 
                    f"Ask plenty of follow-up questions when helpful."
                    f"Make sure to examine all reasons for my belief that I mention."
                    f"5. Ask me additional reasons for my belief, and also examine those additional reasons."
                    f"6. Summarize the conversation."
                    f"7. Ask me how confident I am in my belief after the conversation. Make sure not to judge my response. Don't point out you won't judge it. " 
                    f"8. Thank me for the conversation, and say goodbye. Literally use the word goodbye."
                    f"Don't talk to me about the purpose of the exercise. Do not introduce new facts, and don't be preachy.")

opening_message = "Hi, my name is Diotima. I am a street epistemologist that can help you examine your beliefs. What is your name?"


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
            message_placeholder = st.empty()
            full_response = ""
            
            # Create a list to store the complete prompt sent to OpenAI
            complete_prompt = [{"role": "user", "content": system_message}] + \
                            [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
            # Estimating tokens for the prompt
            prompt_tokens = num_tokens_from_prompt(complete_prompt)
        
            # Send the prompt to OpenAI, and get a response    
            for response in openai.ChatCompletion.create(
                model=st.session_state["openai_model"],
                messages=complete_prompt,
                stream=True,
            ):
                full_response += response.choices[0].delta.get("content", "")
                message_placeholder.markdown(full_response + "▌") 
                # Each response from the stream is one completion token  
                st.session_state["completion_tokens"] += 1         
            
            message_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response, "avatar": "🧑‍🎤"})
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
                db.update_cell(st.session_state["row_number"], conversation_column, output_str)
                # Write name of respondent to db
                db.update_cell(st.session_state["row_number"], name_column, st.session_state.messages[1]["content"])
                # Write number of completion tokens and prompt tokens to db
                db.update_cell(st.session_state["row_number"], completion_tokens_column, st.session_state["completion_tokens"])
                db.update_cell(st.session_state["row_number"], prompt_tokens_column, st.session_state["prompt_tokens"])
else:
    st.chat_input("Write a message", key="input", disabled=True)
    del st.session_state["input"]