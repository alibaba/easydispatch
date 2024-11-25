
import re
# tested in https://regexr.com/

def check_org_str(data):
    if len(data) < 1:
        return False
    # ^[a-zA-Z0-9\$\-#!]*$
    # ^[a-zA-Z0-9]*$
    return bool(re.match(r"^[a-zA-Z0-9\-]*$", data))  # 


def check_order_code_str(data, max_len = 32):
    if data is None:
        return False
    if len(data) < 1:
        return False
    if len(data) > max_len:
        return False
    # Order code can not have -, which is used as -p, -d
    return bool(re.match(r"^[a-zA-Z0-9\$]*$", data))  # 

def check_job_code_str(data, max_len = 32):
    if data is None:
        return False
    if len(data) < 1:
        return False
    if len(data) > max_len:
        return False
    return bool(re.match(r"^[a-zA-Z0-9\$\-]*$", data))  # 

def check_worker_code_str(data):
    if data is None:
        return False
    if data.isnumeric():
        return False
    return bool(re.match(r"^[a-zA-Z0-9\$]*$", data)) 
    # if len(data) < 1:
    #     return False
    # return bool(re.match(r"^[a-zA-Z0-9\$\-#!]*$", data))  # 
