import json

with open("data_cleaning.ipynb", "r") as f:
    nb = json.load(f)

source_code = """import pandas as pd
import re

file_path = "../exports/crop_statistics_raw_20260607_104708.csv"
df = pd.read_csv(file_path)
print(f"Original shape: {df.shape}")

id_vars = ['id', 'State', 'District', 'Year', 'source_record_hash', 'source_dataset', 'source_resource_id', 'source_system', 'ingested_at']
value_vars = [c for c in df.columns if c not in id_vars]

col_meta = []
seasons = ['Kharif', 'Rabi', 'Summer', 'Whole_Year', 'Winter', 'Autumn']

for col in value_vars:
    match = re.search(r'_(Area|Production|Yield)_', col)
    if match:
        metric_start = match.start()
        crop = col[:metric_start]
        rest = col[metric_start + 1:]
        
        season = 'Unknown'
        for s in seasons:
            if rest.endswith('_' + s):
                season = s
                break
        
        if season != 'Unknown':
            metric = rest[:-(len(season)+1)]
        else:
            metric = rest
            season = 'Whole_Year'
            
        col_meta.append({'original_col': col, 'Crop': crop, 'Metric': metric, 'Season': season})
    else:
        col_meta.append({'original_col': col, 'Crop': 'Unknown', 'Metric': 'Unknown', 'Season': 'Unknown'})

df_meta = pd.DataFrame(col_meta)

unknown_cols = df_meta[df_meta['Metric'] == 'Unknown']['original_col'].tolist()
if unknown_cols:
    print(f"Warning: these columns didn't match the pattern and will be ignored: {unknown_cols[:5]}")
    value_vars = [v for v in value_vars if v not in unknown_cols]
    df_meta = df_meta[df_meta['Metric'] != 'Unknown']

# Reshape the dataset from wide to long format
df_long = pd.melt(df, id_vars=id_vars, value_vars=value_vars, var_name='original_col', value_name='Value')
df_long = df_long.merge(df_meta, on='original_col', how='left')
df_long.drop('original_col', axis=1, inplace=True)

# Pivot the dataset so metrics become columns
df_clean = df_long.pivot_table(
    index=id_vars + ['Crop', 'Season'],
    columns='Metric',
    values='Value',
    aggfunc='first'
).reset_index()

# To keep all minor crops and patterns without losing valid sparse data:
# We only drop rows where ALL the metric columns are missing (NaN).
metric_cols = [c for c in df_clean.columns if c not in id_vars + ['Crop', 'Season']]
df_clean.dropna(subset=metric_cols, how='all', inplace=True)

print(f"Cleaned shape: {df_clean.shape}")

# Clean the Crop column (replace _ with space)
df_clean['Crop'] = df_clean['Crop'].str.replace('_', ' ')

# Save the cleaned data
output_path = "../exports/crop_statistics_cleaned.csv"
df_clean.to_csv(output_path, index=False)
print(f"Saved cleaned data to {output_path}")

df_clean.head()"""

lines = [line + "\n" for line in source_code.split("\n")]
lines[-1] = lines[-1].strip("\n") 

nb["cells"][0]["source"] = lines

with open("data_cleaning.ipynb", "w") as f:
    json.dump(nb, f, indent=1)

