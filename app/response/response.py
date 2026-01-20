import uuid
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
    
    1000      -> 成功
    2000-2999 -> [INFO]  业务层消息
    3000-3999 -> [INFO]  外部接口消息
    4000-4999 -> [ERROR] 业务层异常
    5000-5999 -> [ERROR] 外部接口异常
    6000-6999 -> 为前端程序预留
    '''
    API_1000_Success = {'status': 'ok','code': 1000,'message': 'Success','data': None}

    # INFO

    # 输入的服务器参数不正确
    API_2001_IllegalRegion = {'status': 'ok','code': 2001,'message': 'IllegalRegion','data' : None}
    # 输入的用户名称长度不正确
    API_2002_IllegalUserName = {'status': 'ok','code': 2002,'message': 'IllegalUserName','data' : None}
    # 输入的工会名称长度不正确
    API_2003_IllegalClanTag = {'status': 'ok','code': 2003,'message': 'IllegalClanTag','data' : None}
    # 输入的船只名称长度不正确
    API_2004_IllegalShipName = {'status': 'ok','code': 2004,'message': 'IllegalShipName','data' : None}
    # 输入的查询条件匹配船只数量过多
    API_2005_QueryConditionsTooBroad = {'status': 'ok','code': 2005,'message': 'QueryConditionsTooBroad','data' : None}
    # 输入的查询条件为匹配到船只
    API_2006_ShipDataNotMatched = {'status': 'ok','code': 2006,'message': 'ShipDataNotMatched','data' : None}
    # 输入的用户id不合法
    API_2007_IllegalAccoutID = {'status': 'ok','code': 2007,'message': 'IllegalAccoutID','data' : None}
    # 输入的工会id不合法
    API_2008_IllegalClanID = {'status': 'ok','code': 2008,'message': 'IllegalClanID','data' : None}
    # 已达到最大绑定数量限制
    API_2009_MaxBindingLimitReached = {'status': 'ok','code': 2009,'message': 'MaxBindingLimitReached','data' : None}
    # 不存在可以删除的绑定数据
    API_2010_NoBindingData = {'status': 'ok','code': 2010,'message': 'NoBindingData','data' : None}
    # 删除的绑定索引超出范围
    API_2011_BindingIndexOutOfRange = {'status': 'ok','code': 2011,'message': 'BindingIndexOutOfRange','data' : None}
    # 删除的绑定为当前使用中的绑定
    API_2012_CurrentBindingBeDeleted = {'status': 'ok','code': 2012,'message': 'CurrentBindingBeDeleted','data' : None}
    # 删除的绑定为当前使用中的绑定
    API_2013_UserAuthorizationFailed = {'status': 'ok','code': 2013,'message': 'UserAuthorizationFailed','data' : None}

    # 用户未启用recent功能
    API_2014_FeatureNotEnabled = {'status': 'ok','code': 2014,'message': 'FeatureNotEnabled','data' : None}
    # 账号长期未活跃或者隐藏战绩导致自动关闭recent功能
    API_2015_FeatureAutoDisabled = {'status': 'ok','code': 2015,'message': 'FeatureAutoDisabled','data' : None}
    # 账号不符合启用recent功能的条件
    API_2016_AccountNotEligible = {'status': 'ok','code': 2016,'message': 'AccountNotEligible','data' : None}
    # 该账号的RecentPro功能已经启用
    API_2017_FeatureAlreadyEnabled = {'status': 'ok','code': 2017,'message': 'FeatureAlreadyEnabled','data' : None}
    # 需要联系作者进行Recent数据删除
    API_2018_ContactAuthorForDataDeletion = {'status': 'ok','code': 2018,'message': 'ContactAuthorForDataDeletion','data' : None}
    # 普通用户数据记录上限
    # API_2019_DataRetentionLimitDays = {'status': 'ok','code': 2019,'message': 'DataRetentionLimitDays','data' : None}
    # 会员用户数据记录上限
    # API_2020_DataRetentionLimitDays = {'status': 'ok','code': 2020,'message': 'DataRetentionLimitDays','data' : None}
    # 只有启用人才能删除RecentPro资格
    API_2021_RecentDataDeletionFailed = {'status': 'ok','code': 2021,'message': 'RecentDataDeletionFailed','data' : None}
    
    # 生成激活码失败
    API_2022_ActivationCodeGenerationFailed = {'status': 'ok','code': 2022,'message': 'ActivationCodeGenerationFailed','data' : None}
    # 激活码失效
    API_2023_InvalidActivationCode = {'status': 'ok','code': 2023,'message': 'InvalidActivationCode','data' : None}
    # 已使用过该激活码
    API_2024_ActivationCodeAlreadyUsed = {'status': 'ok','code': 2024,'message': 'ActivationCodeAlreadyUsed','data' : None}

    # 用户传入的ac值无效
    API_2025_InvalidAccessToken = {'status': 'ok','code': 2025,'message': 'InvalidAccessToken','data' : None}
    # 用户传入的ac值无效
    API_2026_InvalidAuthToken = {'status': 'ok','code': 2026,'message': 'InvalidAuthToken','data' : None}
    # 
    API_20_ = {'status': 'ok','code': 20,'message': '','data' : None}

    # ERROR

    # 权限不足
    API_4001_PermissionError = {'status': 'ok','code': 4001,'message': 'PermissionError','data' : None}
    MySQL_4100_DatabaseError = {'status': 'ok','code': 4100,'message': 'MySQLDatabaseError','data' : None}
    MySQL_4101_ProgrammingError = {'status': 'ok','code': 4101,'message': 'MySQLProgrammingError','data' : None}
    MySQL_4102_OperationalError = {'status': 'ok','code': 4102,'message': 'MySQLOperationalError','data' : None}
    MySQL_4103_IntegrityError = {'status': 'ok','code': 4103,'message': 'MySQLIntegrityError','data' : None}
    MySQL_4104_DataNotFoundError = {'status': 'ok','code': 4104,'message': 'MySQLDataNotFoundError','data' : None}
    Redis_4200_RedisError = {'status': 'ok','code': 4200,'message': 'RedisError','data' : None}


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
        message: str,
        error_id: str = None
    ) -> ResponseDict:
        "失败的返回值"
        if error_id is None:
            error_id = str(uuid.uuid4())
        return {
            'status': 'error',
            'code': code,
            'message': message,
            'data': {
                'error_id': error_id,
                'platform': 'API'
            }
        }