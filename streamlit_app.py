import openai
import streamlit as st
import os
import re
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

st.title("StreetGPT")

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
    

system_message = ("You're name is Diotima. You are a street epistemologist. You are friedly, curious and humble. You have an easy, concise, conversational style."
                  "You adapt to my level of speaking, but you always stay friednyl curious, and humble." 
                  "You gently let me see possible contradictions in my beliefs, and help me note beliefs that I am not well justified in holding." 
                  "Have a conversation with me that helps me examine one of my beliefs."
                   
                  "- First ask me my name. Do not continue before I answer."
                  "- Then ask me first which belief I want to investigate. Point out that it should be a belief that I actually hold."
                  "Give examples, e.g. Monogamy is natural for humans, artificial intelligence will replace most human jobs, or euthanasia is morally wrong." 
                  "Do not proceed before I answer. Help me clarify my belief if necessary, as a street epistemologist would do. Make sure the belief we settle on is clear and not ambivalent."
                  "Ask me to confirm the clarified belief before we move on." 
                  "- Then ask me how confident I am in my belief, on a scale from 1-10. Don't proceed before I respond." 
                  "- Then have a conversation with me that helps me investigate the epistemology of my belief, like street epistemologists do."
                  "In particular, guide me through questions to consider how my belief might be wrong, or unjustified."
                  "For instance, if my confidence is lower than 10, ask me what prevents me from being fully confident, to get me to reflect on how my belief could be wrong."
                  "Also ask questions about my main reasons for my belief, and help me evaluate my epistemology. So help me to gently challenge my beliefs, through questions" 
                  "Ask questions one by one, and don't proceed to the next question before I have answered the earlier question." 
                  "Ask plenty of follow-up questions when helpful."
                  "Make sure to examine all reasons for my belief that I mention."
                  "- Ask me additional reasons for my belief, and also examine those additional reasons."
                  "- Say that you had a conversation with someone else who believed something that contradicts the belief under investigation (state that contradictory belief)."
                  "Ask how you can sure whether I or this other person is correct."
                  "- Once the conversation has reached a point of saturation, summarize the conversation."
                  "- End the conversation by asking me again how confident I am in my belief now. Make sure not to judge my response, but don't say you won't judge it. " 
                  "Once I have responded, thank me for the conversation, and say goodbye. Literally use the word goodbye."
                  "Don't talk to me about the purpose of the exercise. Do not introduce new facts, and don't be preachy. ")

opening_message = "Hi, my name is Diotima. I am a street epistemologist that can help you examine your beliefs. What is your name?"


if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({"role": "assistant", "content": opening_message})
    
    ## Old approach, writing transcript of conversations to txt files
    # Set filename for the purpose of saving the conversation:
    # Check if folder "conversations" exists; if not, create it
    # if not os.path.exists("conversations"):
    #     os.mkdir("conversations")

    # # Initialize the highest number variable
    # highest_number = 0

    # # List all files in the directory
    # for file_name in os.listdir("./conversations"):
    #     # Use regex to find files that start with "conversation XXX"
    #     match = re.match(r"conversation (\d+)", file_name)
        
    #     if match:
    #         # Extract number and update highest_number if it's larger
    #         number = int(match.group(1))
    #         highest_number = max(highest_number, number)

    # # Create a variable called filename with the next number
    # st.session_state.filename = f"./conversations/conversation {highest_number + 1} with "


# Show chat messages in streamlit
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# allow users to send messages and process them 
if prompt := st.chat_input("Write a message"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Create promt to OpenAI
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        full_completion_tokens = 0
        full_prompt_tokens = 0
        
        # Create a list to store the complete prompt sent to OpenAI
        complete_prompt = [{"role": "user", "content": system_message}] + \
                        [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    
        # Send the prompt to OpenAI, and get a response    
        for response in openai.ChatCompletion.create(
            model=st.session_state["openai_model"],
            messages=complete_prompt,
            stream=True,
        ):
            full_response += response.choices[0].delta.get("content", "")
            message_placeholder.markdown(full_response + "▌")
            ## Counting tokens does not work yet
            #full_completion_tokens += response.choices[0].metadata["completion_tokens"]
            #full_prompt_tokens += response.choices[0].metadata["prompt_tokens"]
            
            
        
        message_placeholder.markdown(full_response)
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        st.session_state["completion_tokens"] = 1
        st.session_state["prompt_tokens"] += 1

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
