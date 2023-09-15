import openai

full_response = ""

for response in openai.ChatCompletion.create(
    api_base="https://streetgpt.openai.azure.com/",
    api_key="c28a0f3d11eb495f80917114a133d26d",
    api_type="azure",
    api_version="2023-07-01-preview",
    engine="StreetGPT",
    messages=[
    {"role": "user", "content": "Hello!"}
    ],
    stream=True,
    max_tokens=16,
    temperature=0,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0,
):
    content_str = None  # Default value

    if 'choices' in response and len(response['choices']) > 0:
        choice = response['choices'][0]
        if 'delta' in choice and 'content' in choice['delta']:
            content_str = choice['delta']['content']

    if content_str:
        full_response += response.choices[0]["delta"]["content"]

print(full_response)

