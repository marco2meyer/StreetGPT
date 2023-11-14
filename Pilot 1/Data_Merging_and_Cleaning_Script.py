
import pandas as pd

# Reading the two Excel files
conversations_path = 'Conversations-3.xlsx'
streetgpt_path = 'StreetGPT_September+8%2C+2023_06.23.xlsx'

df_conversations = pd.read_excel(conversations_path)
df_streetgpt = pd.read_excel(streetgpt_path, skiprows=1)  # Ignoring the first row as per the instruction

# Merging the datasets
merged_df = pd.merge(df_conversations, df_streetgpt, left_on='Response ID', right_on='Response ID', how='inner')

# Dropping rows where 'claim_column' is empty
merged_df_filtered = merged_df.dropna(subset=['claim_column'])

# Replacing specific values in 'statement...' columns
statement_columns = [col for col in merged_df_filtered.columns if col.startswith('statement')]
merged_df_filtered[statement_columns] = merged_df_filtered[statement_columns].replace({
    '1 Completely disagree': 1,
    '10 Completely agree': 10
})

# Replacing specific values in 'To what extent do you agree...' columns
agree_disagree_columns = [col for col in merged_df_filtered.columns if 'To what extent do you agree with the following statement about your interaction with Diotima?' in col]
merged_df_filtered[agree_disagree_columns] = merged_df_filtered[agree_disagree_columns].replace({
    'Strongly agree': 5,
    'Strongly disagree': 1
})

# Converting 'statement...' columns to integers
merged_df_filtered[statement_columns] = merged_df_filtered[statement_columns].apply(pd.to_numeric, errors='coerce')

# Saving the final DataFrame to an Excel file
merged_df_filtered.to_excel('Merged_and_Final_Int_Dataset.xlsx', index=False)
