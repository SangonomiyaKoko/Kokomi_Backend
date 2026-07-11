import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from app.core import EnvConfig

from .typed_dict import (
    ResponseStatus,
    SuccessResponseDict,
    ErrorResponseDict,
    APIFailedResponseDict,
    ResponseDict
)

@dataclass
class BasicResponse:
    """数据接口的基本响应数据结构"""
    mode: str = ''     # 数据模式（pve/pvp/rank/...）
    type: str = ''     # 数据类型（solo/div2/div3/...）
    basic: Dict[str, Any] = field(default_factory=dict)    # 用户或工会的基本信息
    statistics: Dict[str, Any] = field(default_factory=dict)    # 实际统计数据
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'mode': self.mode,
            'type': self.type,
            'basic': self.basic,
            'statistics': self.statistics
        }

class JSONResponse:
    """标准化 JSON 响应工具类

    封装了 API 返回值的构造、预定义状态码常量，以及
    从响应中提取数据的工具方法
    """

    # 部分接口只执行操作而不返回数据，此时返回 API_1000_Success 结果
    API_1000_Success = {'status': 'ok', 'code': 1000, 'message': 'Success', 'data': None}
    
    # 其他返回值
    API_NodeNotAvailable = {'status': 'ok', 'code': 1001, 'message': 'NodeNotAvailable'}
    API_RegionNotSupported = {'status': 'ok', 'code': 1002, 'message': 'RegionNotSupported'}
    API_UserNotExist = {'status': 'ok', 'code': 1003, 'message': 'UserNotExist'}
    API_ClanNotExist = {'status': 'ok', 'code': 1004, 'message': 'ClanNotExist'}
    API_UserDataIsNone = {'status': 'ok', 'code': 1005, 'message': 'UserDataIsNone'}
    API_ClanDataIsNone = {'status': 'ok', 'code': 1006, 'message': 'ClanDataIsNone'}
    API_UseInBlacklist = {'status': 'ok', 'code': 1007, 'message': 'UserInBlacklist'}
    API_ClanInBlacklist = {'status': 'ok', 'code': 1008, 'message': 'ClanInBlacklist'}
    API_UserHiddenProfile = {'status': 'ok', 'code': 1009, 'message': 'UserHiddenProfile'}
    API_AcqurieLockFailed = {'status': 'ok', 'code': 1010, 'message': 'AcqurieLockFailed'}
    API_NoStatisticsData = {'status': 'ok', 'code': 1011, 'message': 'NoStatisticsData'}
    API_RecentNotEnable = {'status': 'ok', 'code': 1012, 'message': 'RecentNotEnable'}
    API_UserNotActive = {'status': 'ok', 'code': 1013, 'message': 'UserNotActive'}
    API_InvalidAccessToken = {'status': 'ok', 'code': 1014, 'message': 'InvalidAccessToken'}
    API_InvalidAuthToken = {'status': 'ok', 'code': 1015, 'message': 'InvalidAuthToken'}

    @staticmethod
    def success(
        data: Optional[Any] = None
    ) -> SuccessResponseDict:
        """构造成功响应

        返回 code=1000 的标准成功响应，附带调用方传入的业务数据。

        Args:
            data: 需要返回给客户端的业务数据，默认为 None。

        Returns:
            SuccessResponseDict
        """
        return {
            'status': ResponseStatus.SUCCESS,
            'code': 1000,
            'message': 'Success',
            'data': data
        }
    
    @staticmethod
    def exception(
        message: str,
        error_id: Optional[str] = None,
        error_name: Optional[str] = None
    ) -> ErrorResponseDict:
        """构造错误响应

        返回指定错误码和错误信息的失败响应，自动生成 trace_id
        并注入当前平台标识，便于后期问题定位

        Args:
            code: 业务错误码，格式遵循类级别定义的分段规则
            message: 面向调用方的错误描述信息
            error_id: 链路追踪 ID。未提供时自动生成 UUID
            error_name: 错误名称，未提供时使用 message

        Returns:
            ErrorResponseDict
        """
        if error_id is None:
            error_id = str(uuid.uuid4())
        return {
            'status': ResponseStatus.ERROR,
            'code': 3000,
            'message': message,
            'error': {
                'trace_id': error_id,
                'node_info': EnvConfig.REGION,
                'error_name': error_name if error_name else message
            }
        }
    
    @staticmethod
    def game_api_failed(
        error_name: str
    ) -> APIFailedResponseDict:
        """构造请求API接口错误响应

        Args:
            error_name: 错误名称或异常类型

        Returns:
            APIFailedResponseDict
        """
        return {
            'status': ResponseStatus.ERROR,
            'code': 2000,
            'message': 'APIFailed',
            'data': {
                'node_info': EnvConfig.REGION,
                'error_name': error_name
            }
        }

    @staticmethod
    def extract_data(response: ResponseDict) -> tuple[bool, Any]:
        """从响应中提取数据

        通过 code 字段判定请求成败：
        - code 不等于 1000：视为失败，返回 (True, 完整响应体)
        - code 等于 1000：视为成功，返回 (False, 响应中的 data 字段)

        Args:
            response: 待提取的响应字典
        """
        if response['code'] != 1000:
            return True, response
        return False, response['data']