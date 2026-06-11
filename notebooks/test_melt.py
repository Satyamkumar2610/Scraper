import pandas as pd
import numpy as np
import re

df = pd.read_csv('../exports/crop_statistics_raw_20260607_104708.csv')
id_vars = ['id', 'State', 'District', 'Year', 'source_record_hash', 'source_dataset', 'source_resource_id', 'source_system', 'ingested_at']
value_vars = [c for c in df.columns if c not in id_vars]

# Melt
df_long = pd.melt(df, id_vars=id_vars, value_vars=value_vars, var_name='Crop_Metric_Season', value_name='Value')

# Extract Crop, Metric, Season
# The pattern is usually {Crop}_(Area_Hectare|Production_Tonnes|Yield_Tonne_Hectare)_{Season}
# Let's see if we can extract this cleanly
def parse_col(col):
    match = re.search(r'_(Area_Hectare|Production_Tonnes|Yield_Tonne_Hectare)_', col)
    if match:
        metric = match.group(1)
        parts = col.split('_' + metric + '_')
        crop = parts[0]
        season = parts[1] if len(parts) > 1 else ''
        return crop, metric, season
    return None, None, None

df_long[['Crop', 'Metric', 'Season']] = df_long['Crop_Metric_Season'].apply(lambda x: pd.Series(parse_col(x)))

# Pivot the metrics to columns
df_clean = df_long.pivot_table(index=id_vars + ['Crop', 'Season'], columns='Metric', values='Value', aggfunc='first').reset_index()

# Drop rows where all metrics are NaN
metric_cols = [m for m in ['Area_Hectare', 'Production_Tonnes', 'Yield_Tonne_Hectare'] if m in df_clean.columns]
df_clean = df_clean.dropna(subset=metric_cols, how='all')

print("Original shape:", df.shape)
print("Clean shape:", df_clean.shape)
print(df_clean.head())
