from typing import Optional, Literal, Union, Any, Dict, List
from typing_extensions import TypedDict

class ResponseDict(TypedDict):
    '''返回数据格式'''
    status: Literal['ok', 'error']
    code: int
    message: str
    data: Optional[Union[Dict, List]]

class JSONResponse:
    '''接口返回值
    
    对于code是1000 2000~2003 3000 4000 5000的返回值，请使用内置函数获取response

    对于返回值的描述，请查看设计文档
    '''
    API_1000_Success = {'status': 'ok','code': 1000,'message': 'Success','data': None}

    # INFO

    # 用户不存在(未注册或已删除)
    API_3001_UserNotExist = {'status': 'ok','code': 3001,'message': 'UserNotExist','data' : None}
    # 工会不存在(未注册或已删除)
    API_3002_ClanNotExist = {'status': 'ok','code': 3002,'message': 'ClanNotExist','data' : None}
    # 用户数据为空
    API_3003_UserDataisNone = {'status': 'ok','code': 3003,'message': 'UserDataisNone','data' : None}
    # 工会数据为空
    API_3004_ClanDataisNone = {'status': 'ok','code': 3004,'message': 'ClanDataisNone','data' : None}
    # 用户隐藏战绩
    API_3005_UserHiddenProfite = {'status': 'ok','code': 3005,'message': 'UserHiddenProfite','data' : None}
    # token1已失效
    API_3006_Token1isInvalid = {'status': 'ok','code': 3006,'message': 'Token1isInvalid','data' : None}
    # token2已失效
    API_3007_Token2isInvalid = {'status': 'ok','code': 3007,'message': 'Token2isInvalid','data' : None}
    # 未读取到船只数据
    API_3008_VehiclesDataLoadFailed = {'status': 'ok','code': 3008,'message': 'VehiclesDataLoadFailed','data' : None}
    # 未读取到船只数据
    API_3009_NoVehiclesChangesFound = {'status': 'ok','code': 3009,'message': 'NoVehiclesChangesFound','data' : None}
    # 用户名称未有匹配结果
    API_3010_UserNameNotFound = {'status': 'ok','code': 3010,'message': 'UserNameNotFound','data' : None}
    # 工会名称未有匹配结果
    API_3011_ClanNameNotFound = {'status': 'ok','code': 3011,'message': 'ClanNameNotFound','data' : None}
    # 从官方api接口获取数据失败
    API_3012_FailedToFetchDataFromAPI = {'status': 'ok','code': 3012,'message': 'FailedToFetchDataFromAPI','data' : None}

    # ERROR

    Httpx_5000_NetworkError = {'status': 'error','code': 5000,'message': 'NetworkError','data' : None}
    Httpx_5001_ConnectTimeout = {'status': 'error','code': 5001,'message': '','data' : None}
    Httpx_5002_ReadTimeout = {'status': 'error','code': 5002,'message': 'HttpxReadTimeout','data' : None}
    Httpx_5003_TimeoutError = {'status': 'error','code': 5003,'message': 'HttpxTimeoutError','data' : None}
    Httpx_5004_ConnectError = {'status': 'error','code': 5004,'message': 'HttpxConnectError','data' : None}
    Httpx_5005_ReadError = {'status': 'error','code': 5005,'message': 'HttpxReadError','data' : None}
    Httpx_5006_HTTPStatusError = {'status': 'error','code': 5006,'message': 'HttpxHTTPStatusError','data' : None}

    @staticmethod
    def get_success_response(
        data: Optional[Any] = None
    ) -> ResponseDict:
        "成功的返回值"
        return {
            'status': 'ok',
            'code': 1000,
            'message': 'Success',
            'data': data
        }
    
    @staticmethod
    def get_error_response(
        code: str,
        message: str
    ) -> ResponseDict:
        "失败的返回值"
        return {
            'status': 'error',
            'code': code,
            'message': message,
            'data': None
        }