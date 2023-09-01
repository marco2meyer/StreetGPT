import openai
import streamlit as st
import os
import re

st.title("StreetGPT")

openai.api_key = st.secrets["OPENAI_API_KEY"]

if "openai_model" not in st.session_state:
    st.session_state["openai_model"] = "gpt-4"

system_message = ("You're name is SocratAI. You are a street epistemologist. You are friedly, curious and humble. You have an easy, concise, conversational style." 
                  "You are good in gently letting people see possible contradictions in their beliefs, and notice beliefs that they are not well justified in holding." 
                  "Have a conversation with me that helps me examine my beliefs." 
                  "First ask me my name. Do not continue before I answer."
                  "Then ask me first which belief I want to investigate." 
                  "Do not proceed before I answer. Help me clarify my belief if necessary, as a street epistemologist would." 
                  "Then ask me how confident I am in my belief, on a scale. Don't proceed before I respond." 
                  "Then have a conversation with me that helps me investigate the epistemology of my belief, like street epistemologists do."
                  "For instance, ask questions about my main reasons for my belief, and help me evaluate my epistemology." 
                  "Ask questions one by one, and don't proceed to the next question before I have answered the earlier question." 
                  "Ask plenty of follow-up questions when helpful."
                  "Make sure to examine all reasons for my belief that I mention."
                  "Before ending the conversation, ask me additional reasons for my belief, and also examine those additional reasons."
                  "End the conversation by asking me again how confident I am in my belief now." 
                  "Once I have told you, thank me for the conversation, and say goodbye"
                  "Don't talk to me about the purpose of the exercise. Do not introduce new facts, and don't be preachy. ")

opening_message = "Hi, I am SocratAI. I am a street epistemologist that can help you examine your beliefs. What is your name?"


if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({"role": "assistant", "content": opening_message})
    
    ##Set filename for the purpose of saving the conversation:
    # Check if folder "conversations" exists; if not, create it
    if not os.path.exists("conversations"):
        os.mkdir("conversations")

    # Initialize the highest number variable
    highest_number = 0

    # List all files in the directory
    for file_name in os.listdir("./conversations"):
        # Use regex to find files that start with "conversation XXX"
        match = re.match(r'conversation (\d+)', file_name)
        
        if match:
            # Extract number and update highest_number if it's larger
            number = int(match.group(1))
            highest_number = max(highest_number, number)

    # Create a variable called filename with the next number
    st.session_state.filename = f"./conversations/conversation {highest_number + 1} with "



for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Write a message"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # Create a list to store the complete prompt sent to OpenAI
        complete_prompt = [{"role": "user", "content": system_message}] + \
                        [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
        
        for response in openai.ChatCompletion.create(
            model=st.session_state["openai_model"],
            messages=complete_prompt,
            stream=True,
        ):
            full_response += response.choices[0].delta.get("content", "")
            message_placeholder.markdown(full_response + "▌")
        
        message_placeholder.markdown(full_response)
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        
        # Write the complete prompt and response to a file
        if len(st.session_state.messages) > 1:
            filename = st.session_state.filename + st.session_state.messages[1]["content"] + ".txt"
            with open(filename, 'w') as f:                
                for message in complete_prompt[1:]:
                    f.write(f"{message['role']}: {message['content']}\n")                
                f.write(f"assistant: {full_response}\n")

