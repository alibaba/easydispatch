from dispatch.config import ED_JAVA_URL, ED_JAVA_URL_TIMEOUT
from urllib3.util.retry import Retry

import requests
from requests.adapters import HTTPAdapter

from dispatch.order.models import  UploadOssFile


session = requests.Session()
retry = Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)


import logging
log = logging.getLogger(__name__)


'''
获取 oss 签名 
'''
def get_oss_signature(scenarioCode ,fileSize,fileName,user_id,token):
        '''
        
        {
        "code": "S0000",
        "data": {
            "accessId": "5JK9n2yWStiegAGj",
            "callback": "eyJjYWxsYmFja0JvZHlUeXBlIjoiYXBwbGljYXRpb24vanNvbiIsImNhbGxiYWNrVXJsIjoiaHR0cHM6Ly9lYXN5ZGlzcGF0Y2guZGF0YS5hbGl5dW4uY29tL2Vhc3lkaXNwYXRjaC92MS9jb21tb24vZmlsZS9vc3NDYWxsYmFjayIsImNhbGxiYWNrQm9keSI6IntcImZpbGVDb2RlXCI6XCIyMDIyMDkyMjE3MDYzNjAwMDAxXCIsXCJzY2VuYXJpb0NvZGVcIjpcImVkX3dvcmtlcl9hcHBfaW1hZ2VcIixcIm9wZXJhdG9ySWRcIjpcInJpZGVyXCJ9In0=",
            "callbackUrl": "eyJjYWxsYmFja0JvZHlUeXBlIjoiYXBwbGljYXRpb24vanNvbiIsImNhbGxiYWNrVXJsIjoiaHR0cHM6Ly9lYXN5ZGlzcGF0Y2guZGF0YS5hbGl5dW4uY29tL2Vhc3lkaXNwYXRjaC92MS9jb21tb24vZmlsZS9vc3NDYWxsYmFjayIsImNhbGxiYWNrQm9keSI6IntcImZpbGVDb2RlXCI6XCIyMDIyMDkyMjE3MDYzNjAwMDAxXCIsXCJzY2VuYXJpb0NvZGVcIjpcImVkX3dvcmtlcl9hcHBfaW1hZ2VcIixcIm9wZXJhdG9ySWRcIjpcInJpZGVyXCJ9In0=",
            "dir": "ed_worker_app/image/",
            "expire": "1663839396",
            "fileCode": "2022092217063600001",
            "host": "https://alicloud-file.oss-ap-southeast-1.aliyuncs.com",
            "ossContentDisposReqHeaderByFileName": "卡卡西.png",
            "policy": "eyJleHBpcmF0aW9uIjoiMjAyMi0wOS0yMlQwOTozNjozNi42MzRaIiwiY29uZGl0aW9ucyI6W1siY29udGVudC1sZW5ndGgtcmFuZ2UiLDAsNTI1MDAwMF0sWyJzdGFydHMtd2l0aCIsIiRrZXkiLCIiXV19",
            "signature": "WUhEAmbt9kG/wfJArTyLNpD5azQ="
        },
        "message": "操作成功",
        "result": "success",
        "timestamp": "20220922170636"
        }
        '''

        url = f"{ED_JAVA_URL}/common/file/oss_signature"
        headers = {"content-type": "application/json","User-Token":str(user_id),"token":token}
        params = {"scenarioCode": scenarioCode, "fileSize": fileSize,"fileName":fileName}
        response = session.post(url=url, headers=headers, json=params, timeout=ED_JAVA_URL_TIMEOUT)
        data = None
        try:
            resp_json = response.json()
            if resp_json["result"] != "success":
                log.error(f"EdJavaError: Failed to get get_oss_signature: fileName {fileName} :{resp_json}")
                return None           
            data =  resp_json["data"]
        except KeyError:
            log.error(f"EdJavaError: Failed to get get_oss_signature: fileName {fileName} :{resp_json}")
            return None
        return  data

'''
/delivery/order/update_order_status
订单 - 更新订单状态
'''

def update_order_status(orderCode ,targetStatus,reasonCode, fileCode, token,user_id):
        result_data = {
                "msg": '',
                "flag": False,
            }
        url = f"{ED_JAVA_URL}/delivery/order/update_order_status"
        headers = {"content-type": "application/json","User-Token":str(user_id),"token":token}
        params = {"orderCode": orderCode, "targetStatus": targetStatus,"reasonCode":reasonCode, "fileCode": fileCode}
        # log.info("debugging deployment....")
        response = session.post(url=url, headers=headers, json=params, timeout=ED_JAVA_URL_TIMEOUT)
        try:
            resp_json = response.json()
            if resp_json["result"] != "success":
                log.error(f"EdJavaError: Failed to get update_order_status: orderCode {orderCode} :{resp_json}")
                result_data['msg']= resp_json["message"]   
            else:
                result_data['flag']=True
                result_data['msg'] =  resp_json["data"]
        except KeyError:
            error_info = f"EdJavaError KeyError: Failed to get update_order_status: orderCode {orderCode} :{resp_json}"
            log.error(error_info)
            result_data['msg']= error_info
        except:
            error_info = f"EdJavaError others: Failed to get update_order_status: respnose: {response} "
            log.error(error_info)
            result_data['msg']= error_info
        return result_data

'''
/delivery/order/update_order_location
订单 - 更新配送单地址
'''

def update_order_location(orderCode ,locationId,customerAddress,token,user_id):

    url = f"{ED_JAVA_URL}/delivery/order/update_order_location"
    headers = {"content-type": "application/json","User-Token":str(user_id),"token":token}
    params = {"orderCode": orderCode, "locationId": locationId,"customerAddress":customerAddress}
    response = session.post(url=url, headers=headers, json=params, timeout=ED_JAVA_URL_TIMEOUT)
    data = None
    try:
        resp_json = response.json()
        if resp_json["result"] != "success":
            log.error(f"EdJavaError: result code, Failed to update_order_location: orderCode {orderCode} :reponse: {resp_json}, params:{params}")
            return None           
        data =  resp_json["data"]
        log.info(f"EdJavaInfo: update_order_location done: orderCode {orderCode}")
    except KeyError:
        log.error(f"EdJavaError: KeyError, Failed to get update_order_location: orderCode {orderCode} :reponse: {resp_json} :params:{params}")
        return None
    return  data


'''
/easydispatch/api/v1/account/user/pc_logout
Logout - after changing password
'''

def trigger_pc_logout(token,target_user_id, current_user_id):

    url = f"{ED_JAVA_URL}/account/user/pc_logout?userId={target_user_id}"
    headers = {"User-Token":str(current_user_id),"token":token} 
    try:
        response = session.get(url=url, headers=headers, timeout=ED_JAVA_URL_TIMEOUT)
        data = None 
        log.info(f"EdJavaInfo: successful trigger_pc_logout: user_id {target_user_id}, {response.text}  ") 

    except Exception as e:
        log.error(f"EdJavaError: Failed totrigger_pc_logout: user_id {target_user_id}  ") 




'''
文件上传 oss
'''
def oss_file_upload(images_oss:UploadOssFile,file):
        url = images_oss.url
        headers = {"content-type": "multipart/form-data",'Accept': '*/*'}
        params = images_oss.dict(skip_defaults=True,exclude={'url'})
        params['file'] = file
        response = session.post(url=url, headers=headers, json=params, timeout=ED_JAVA_URL_TIMEOUT,verify=False)
        data = None
        try:
            resp_json = response.json()
            if resp_json["result"] != "success":
                log.error(f"EdJavaError: Failed to oss_file_upload: key {images_oss.key} :{resp_json}")
                return None           
            data =  resp_json["data"]
        except KeyError:
            log.error(f"EdJavaError: Failed to oss_file_upload: images_oss  {images_oss.key} :{resp_json}")
            return None
        return  data





def query_file_url(file_code_list,user_id,token):

        result_data = []

        for file_code in file_code_list:
            try:
                url = f"{ED_JAVA_URL}/common/file/query_file_url?fileCode={file_code}"
                headers = {"content-type": "application/json","User-Token":str(user_id),"token":token}
                response = session.get(url=url, headers=headers, timeout=ED_JAVA_URL_TIMEOUT)
                data = ''
                try:
                    resp_json = response.json()
                    if resp_json["result"] != "success":
                        log.error(f"EdJavaError: Failed to query_file_url: file_code {file_code} :{resp_json}")
                        return None           
                    data =  resp_json["data"]
                except KeyError:
                    log.error(f"EdJavaError: Failed to query_file_url: file_code {file_code} :{resp_json}")
                    return None
                
                if data:
                    result_data.append({"file_code":file_code,"url":data})

            except Exception as e:
                    log.error(f"EdJavaError: Failed to query_file_url: file_code {file_code} :{e}")

        return  result_data


'''
/easydispatch/api/v1/job/job_biz/redliver
pc点击重新配送
'''

def do_redliver(order_code,token,user_id):

        url = f"{ED_JAVA_URL}/job/job_biz/redliver"
        headers = {"content-type": "application/json","User-Token":str(user_id),"token":token}
        params = {"orderId": order_code}
        response = session.post(url=url, headers=headers, json=params, timeout=ED_JAVA_URL_TIMEOUT)
        status = 1
        message = 'success'
        try:
            resp_json = response.json()
            if resp_json["result"] != "success":
                status = 0
                message =str(resp_json['message'])
                log.error(f"EdJavaError: Failed to post redliver: order_code {order_code} :{resp_json}")
                return {
                    "status":status,
                    "message":message,
                }           
            
            message =str(resp_json['message'])
        except KeyError:
            status = 0
            message =str(resp_json['message'])
            log.error(f"EdJavaError: Failed to post redliver: order_code {order_code} :{resp_json}")
        return {
                    "status":status,
                    "message":message,
                } 

