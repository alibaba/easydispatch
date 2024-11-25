
import pandas as pd
import json
from pandas import json_normalize
import time

from datetime import timedelta, datetime

from collections import defaultdict

now = time.strftime("%Y-%m-%d", time.localtime())

data_filter = defaultdict(list)

over_data = {"data": []}
with open('./output/output_jobs.json', 'r') as f:
    over_data = json.load(f)

_filter_data = [order for order in over_data["data"] if now == order['addTime'].split()[0]]
# excel_data_list = json.loads(excel_data_list)
df = json_normalize(_filter_data)
now = time.strftime("%Y-%m-%d", time.localtime())
file_path = f"./output/output_jobs_{now}.csv"
# writer = pd.ExcelWriter(file_path)

# df.to_excel(writer,
#           columns=["worker_code", "job_type", "start_x", "start_y", "end_x", "end_y", "state", "add_time", "finish_time", "cancel_time", "state1_time", "state2_time", "state3_time", "state4_time"],
#           index=False,
#           encoding='utf-8',
#           sheet_name='Sheet')

df.to_csv(file_path, encoding='utf-8', index=False)
print(f"save job succeed :{file_path}")
