import pandas as pd
excel_file = "exports/crop_statistics_raw_20260605_223342.xlsx"
csv_file = "exports/crop_statistics_raw_20260607_104708.csv"

df_csv = pd.read_csv(csv_file, nrows=0)
df_excel = pd.read_excel(excel_file, nrows=0)

csv_cols = set(df_csv.columns)
excel_cols = set(df_excel.columns)

print("In CSV but not Excel:", csv_cols - excel_cols)
print("In Excel but not CSV:", excel_cols - csv_cols)
print(f"Total CSV cols: {len(csv_cols)}, Total Excel cols: {len(excel_cols)}")
