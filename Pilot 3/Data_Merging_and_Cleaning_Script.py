
import pandas as pd
import numpy as np

# Function to determine condition
def determine_condition(row):
    if pd.notna(row['Reasons']):
        return 'reasons'
    elif pd.notna(row['NegReasons']):
        return 'neg_reasons'
    elif pd.notna(row['Diotima']):
        return 'diotima'
    elif pd.notna(row['Control']):
        return 'control'
    else:
        return 'unclear'


# Reading the three Excel files
conversations_path = 'conversations.xlsx'
#I conducted data collection in two installments: first the three experimental condition, then the control condition
qualtrics_path = 'qualtrics.xlsx'
qualtrics_control_path = 'qualtrics_control.xlsx'

df_conversations = pd.read_excel(conversations_path)
df_qualtrics = pd.read_excel(qualtrics_path, skiprows=[1])  # Ignoring the first row as per the instruction
df_qualtrics_control = pd.read_excel(qualtrics_control_path, skiprows=[1])  # Ignoring the first row as per the instruction

# Merge qualtrics dfs

# Add a temporary 'order' column to remember the original row order
df_qualtrics['order'] = range(len(df_qualtrics))
df_qualtrics_control['order'] = range(len(df_qualtrics), len(df_qualtrics) + len(df_qualtrics_control))


# Identify common columns that are not keys for merging
common_cols = set(df_qualtrics.columns).intersection(set(df_qualtrics_control.columns)) - {'ResponseId'}

merged_qualtrics = pd.merge(df_qualtrics, df_qualtrics_control, on='ResponseId', how='outer')

# Combine data under common columns
for col in common_cols:
    merged_qualtrics[col] = merged_qualtrics[col + '_x'].combine_first(merged_qualtrics[col + '_y'])
    merged_qualtrics.drop([col + '_x', col + '_y'], axis=1, inplace=True)



# Reorder columns to match df1, appending any new columns from df2
new_columns = [col for col in df_qualtrics.columns] + \
              [col for col in df_qualtrics_control.columns if col not in df_qualtrics.columns]
merged_qualtrics = merged_qualtrics[new_columns]



# Merging the datasets
merged_df = pd.merge(merged_qualtrics, df_conversations, left_on='ResponseId', right_on='Response ID', how='left')


# Dropping Preview rows
merged_df_filtered = merged_df[merged_df['Status'] != 'Survey Preview']

# Sort by the 'order' column to have df1 rows first, then df2 rows
merged_qualtrics.sort_values(by='order', inplace=True)
merged_qualtrics.drop('order', axis=1, inplace=True)


# Determine survey condition:
merged_df_filtered.rename(columns={"NegReasons ": "NegReasons"}, inplace=True)
merged_df_filtered['Condition'] = merged_df_filtered.apply(determine_condition, axis=1)
# Drop unclear condition
merged_df_filtered = merged_df_filtered[merged_df_filtered['Condition'] != 'unclear']


# Replacing specific values in Conspiracy columns
statement_columns = [col for col in merged_df_filtered.columns if col.endswith('Q4')] + ["Credence_post"]
merged_df_filtered[statement_columns] = merged_df_filtered[statement_columns].replace({
    '1 Completely disagree': 1,
    '10 Completely agree': 10
}).apply(pd.to_numeric, errors='coerce')

# Replacing specific values in 'EVS' columns
evs_columns = [col for col in merged_df_filtered.columns if col.endswith('EVS')]
merged_df_filtered[evs_columns] = merged_df_filtered[evs_columns].replace({
    'Strongly agree': 5,
    'Strongly disagree': 1
}).apply(pd.to_numeric, errors='coerce')

# Replacing specific values in importance columns
merged_df_filtered["Importance"] = merged_df_filtered["Importance"].replace({
    '1 Not at all important': 1,
    '10 Very important': 10
}).apply(pd.to_numeric, errors='coerce')

## Get rid of duplicates
duplicate_response_ids = merged_df_filtered[merged_df_filtered.duplicated('ResponseId', keep=False)].sort_values('ResponseId')

# Calculate the number of NaN values in each row
merged_df_filtered['nan_count'] = merged_df_filtered.apply(lambda x: x.isna().sum(), axis=1)

# Sort the DataFrame by 'ResponseId' and 'nan_count'
merged_df_filtered = merged_df_filtered.sort_values(by=['ResponseId', 'nan_count'], ascending=[True, True])

# Remove duplicates based on 'ResponseId', keeping the first (which has fewer NaN values after sorting)
merged_df_filtered = merged_df_filtered.drop_duplicates(subset='ResponseId', keep='first')

# Drop the 'nan_count' column as it's no longer needed
merged_df_filtered.drop('nan_count', axis=1, inplace=True)

# Show some rows to confirm that duplicates have been removed
merged_df_filtered[merged_df_filtered['ResponseId'].isin(duplicate_response_ids['ResponseId'])]




# Saving the final DataFrame to an Excel file
merged_df_filtered.to_excel('Merged_and_Final_Int_Dataset.xlsx', index=False)
