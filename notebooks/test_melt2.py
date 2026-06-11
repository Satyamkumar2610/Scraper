import pandas as pd
import re

file_path = "../exports/crop_statistics_raw_20260607_104708.csv"
df = pd.read_csv(file_path)

id_vars = ['id', 'State', 'District', 'Year', 'source_record_hash', 'source_dataset', 'source_resource_id', 'source_system', 'ingested_at']
value_vars = [c for c in df.columns if c not in id_vars]

col_meta = []
for col in value_vars:
    match = re.search(r'_(Area_Hectare|Production_Tonnes|Yield_Tonne_Hectare)_', col)
    if match:
        metric = match.group(1)
        parts = col.split('_' + metric + '_')
        crop = parts[0]
        season = parts[1] if len(parts) > 1 else ''
        col_meta.append({'original_col': col, 'Crop': crop, 'Metric': metric, 'Season': season})
    else:
        # Check if the column is just crop and metric
        match = re.search(r'_(Area_Hectare|Production_Tonnes|Yield_Tonne_Hectare)$', col)
        if match:
            metric = match.group(1)
            parts = col.split('_' + metric)
            crop = parts[0]
            col_meta.append({'original_col': col, 'Crop': crop, 'Metric': metric, 'Season': 'Whole_Year'})
        else:
            col_meta.append({'original_col': col, 'Crop': 'Unknown', 'Metric': 'Unknown', 'Season': 'Unknown'})

df_meta = pd.DataFrame(col_meta)

# Drop any columns that are 'Unknown' Metric, just to be safe
unknown_cols = df_meta[df_meta['Metric'] == 'Unknown']['original_col'].tolist()
if unknown_cols:
    print(f"Warning: these columns didn't match the pattern and will be ignored: {unknown_cols[:5]}")
    value_vars = [v for v in value_vars if v not in unknown_cols]
    df_meta = df_meta[df_meta['Metric'] != 'Unknown']

df_long = pd.melt(df, id_vars=id_vars, value_vars=value_vars, var_name='original_col', value_name='Value')
df_long = df_long.merge(df_meta, on='original_col', how='left')
df_long.drop('original_col', axis=1, inplace=True)

df_clean = df_long.pivot_table(
    index=id_vars + ['Crop', 'Season'],
    columns='Metric',
    values='Value',
    aggfunc='first'
).reset_index()

metric_cols = [c for c in ['Area_Hectare', 'Production_Tonnes', 'Yield_Tonne_Hectare'] if c in df_clean.columns]
df_clean.dropna(subset=metric_cols, how='all', inplace=True)

print("Original shape:", df.shape)
print("Clean shape:", df_clean.shape)
print(df_clean.head())
