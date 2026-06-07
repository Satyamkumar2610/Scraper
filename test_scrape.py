import requests
import pandas as pd
from io import StringIO

session = requests.Session()
session.verify = False
res = session.get("https://data.desagri.gov.in/website/crops-apy-report-web", verify=False)
import re
match = re.search(r'name="_token" value="([^"]+)"', res.text)
token = match.group(1)

data = {
    'reportformat': 'horizontal_crop_vertical_year',
    '_token': token,
    'fltrstates[]': '9', # Uttar Pradesh
    'fltrstartyear': '1997',
    'fltrendyear': '1998'
}
url = "https://data.desagri.gov.in/report/crop/horizontal_crop_vertical_year"
res = session.post(url, data=data, verify=False)
tables = pd.read_html(StringIO(res.text))
df = tables[0]
print("MultiIndex Columns:")
for i, col in enumerate(df.columns.values[:10]):
    print(f"{i}: {col}")
print("First row data:")
print(df.iloc[0, :5].tolist())
