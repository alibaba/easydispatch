
# 开发调试 中 的辅助工具, 主要用来测试 那些数字对应的日期 , 或日期对应的数字 
# 以及 redis 联通测试
from datetime import datetime, timedelta
from dispatch.config import (
    DATA_START_DAY,
)
import dispatch.config as kandbox_config

data_start_datetime = datetime.strptime(
            DATA_START_DAY, kandbox_config.KANDBOX_DATE_FORMAT
        )
KANDBOX_DATETIME_FORMAT_ISO_SPACE = "%Y-%m-%d %H:%M:%S"




def number_to_date(num ):
    return data_start_datetime + timedelta(minutes=num)
    
def date_to_number(num):
    result = (datetime.strptime(num, KANDBOX_DATETIME_FORMAT_ISO_SPACE) - datetime.strptime("2023-02-15 00:00:00", KANDBOX_DATETIME_FORMAT_ISO_SPACE)).seconds
    
    print(num, result)
    
    return result
    
    

if __name__ == "__main__":
    
    print(number_to_date(73140)) 
    print()
    date_to_number("2023-07-10 12:08:00")
