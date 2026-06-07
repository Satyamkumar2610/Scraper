import pandas as pd

excel_file = "exports/crop_statistics_raw_20260605_223342.xlsx"
csv_file = "exports/crop_statistics_raw_20260607_104708.csv"

print("Checking CSV (First 5 rows to be fast)...")
df_csv = pd.read_csv(csv_file, nrows=5)
print(f"CSV Columns ({len(df_csv.columns)}):", list(df_csv.columns))

print("\nChecking Excel (First 5 rows to be fast)...")
df_excel = pd.read_excel(excel_file, nrows=5)
print(f"Excel Columns ({len(df_excel.columns)}):", list(df_excel.columns))

# If columns match
if list(df_csv.columns) == list(df_excel.columns):
    print("\nSUCCESS: Both files have the exact same columns and structure!")
else:
    print("\nWARNING: Columns are different!")
