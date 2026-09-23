import json
from datetime import datetime, timezone
from typing import Dict, Any

import math

from app.core import EnvConfig
from app.middlewares import RedisClient
from app.models import PlatformModel

from .metrics import ServiceMetrics

def _is_dev_mode() -> bool:
    return EnvConfig.DEV_MODE


def _dev_overview():
    empty_24h = [[f"{h:02d}:00" for h in range(24)], [0] * 24]
    empty_30d = [[], []]
    return {
        "cards": [
            {"title": "Monthly Requests", "value": "0", "icon": "📊", "color": "#f59e0b"},
            {"title": "Today's API Calls", "value": "0", "icon": "📡", "color": "#667eea"},
            {"title": "Average Response Time", "value": "0ms", "icon": "⚡", "color": "#f093fb"},
            {"title": "Success Rate (200)", "value": "0%", "icon": "✅", "color": "#43e97b"},
            {"title": "Active Services", "value": "0 / 5", "icon": "🖥️", "color": "#4facfe"},
        ],
        "overview_chart_json": json.dumps({
            "labels": empty_24h[0], "request_values": empty_24h[1], "avg_response_values": empty_24h[1],
        }),
        "monthly_line_chart_json": json.dumps({
            "labels": empty_30d[0], "values": empty_30d[1],
        }),
    }


def _dev_celery():
    empty_30d = [[], []]
    return {
        "cards": [
            {"title": "Monthly Processed", "value": "--", "icon": "📊", "color": "#f59e0b"},
            {"title": "Today's Processed", "value": "--", "icon": "📡", "color": "#667eea"},
            {"title": "Pending Tasks", "value": "--", "icon": "📦", "color": "#4facfe"},
            {"title": "Consumers", "value": "--", "icon": "🔗", "color": "#43e97b"},
            {"title": "Today's Failed", "value": "0", "icon": "❌", "color": "#fa709a"},
        ],
        "celery_chart_json": json.dumps({
            "labels": empty_30d[0], "values": empty_30d[1],
        }),
        "celery_error_chart_json": json.dumps({
            "labels": empty_30d[0], "values": empty_30d[1],
        }),
    }


def _dev_game_api():
    empty_30d = [[], []]
    return {
        "cards": [
            {"title": "Monthly Requests", "value": "--", "icon": "📊", "color": "#f59e0b"},
            {"title": "Today's Requests", "value": "--", "icon": "📡", "color": "#667eea"},
            {"title": "Today's Failed", "value": "--", "icon": "⚠️", "color": "#fa709a"},
            {"title": "Failure Rate", "value": "--", "icon": "❌", "color": "#ef4444"},
            {"title": "Reserved", "value": "--", "icon": "📋", "color": "#4facfe"},
        ],
        "http_total_chart_json": json.dumps({"labels": empty_30d[0], "values": empty_30d[1]}),
        "http_error_rate_chart_json": json.dumps({"labels": empty_30d[0], "values": empty_30d[1]}),
    }


def _dev_user_activity():
    return {
        "planned_users": 0,
        "planned_clans": 0,
        "user_level_chart_json": json.dumps({"legend": [], "data": []}),
        "refresh_plan_chart_json": json.dumps({"legend": [], "data": []}),
        "activity_chart_json": json.dumps({"labels": [], "values": []}),
        "hourly_chart_json": json.dumps({"labels": [], "user_values": [], "clan_values": []}),
    }


async def get_overview_data() -> Dict[str, Any]:
    """概览页数据"""
    if _is_dev_mode():
        return _dev_overview()

    now = datetime.now(timezone.utc)
    today = now.date()
    log_dir = EnvConfig.LOG_DIR

    # 1. 获取今日请求统计（含每小时平均响应时间）
    total_count, buckets, avg_elapsed_ms, status_200_count, hourly_avg_elapsed = ServiceMetrics.get_hourly_request_stats(today, log_dir)

    # 2. 构建24小时图表数据
    hourly_keys, hourly_values = ServiceMetrics.build_hourly_chart_data(now, buckets)

    # 3. 获取30天API调用统计
    monthly_keys, monthly_values = await ServiceMetrics.get_monthly_api_stats(now)

    # 4. 获取本月总计请求数据
    month_key = now.strftime("%Y-%m")
    monthly_total_result = await RedisClient.get(f"metrics:api:monthly:{month_key}")
    monthly_total = monthly_total_result['data'] if monthly_total_result['code'] == 1000 and monthly_total_result['data'] else 0
    monthly_total = int(monthly_total)

    # 5. 获取服务状态
    active_services, total_services = await ServiceMetrics.get_services_status()

    # 6. 构建24h平均响应时间图表数据
    _, hourly_avg_values = ServiceMetrics.build_hourly_chart_data(now, hourly_avg_elapsed)

    # 组装返回数据
    success_rate = 0 if total_count == 0 else round(status_200_count / total_count * 100, 1)

    return {
        "cards": [
            {
                "title": "Monthly Requests",
                "value": f"{monthly_total:,}",
                "icon": "📊",
                "color": "#f59e0b"
            },
            {
                "title": "Today's API Calls",
                "value": f"{total_count:,}",
                "icon": "📡",
                "color": "#667eea"
            },
            {
                "title": "Average Response Time",
                "value": f"{avg_elapsed_ms}ms",
                "icon": "⚡",
                "color": "#f093fb"
            },
            {
                "title": "Success Rate (200)",
                "value": f"{success_rate}%",
                "icon": "✅",
                "color": "#43e97b"
            },
            {
                "title": "Active Services",
                "value": f"{active_services} / {total_services}",
                "icon": "🖥️",
                "color": "#4facfe"
            }
        ],
        "overview_chart_json": json.dumps({
            "title": "24-Hour API Requests & Avg Response Time",
            "yAxisName": "Count",
            "labels": hourly_keys,
            "request_values": hourly_values,
            "avg_response_values": hourly_avg_values
        }),
        "monthly_line_chart_json": json.dumps({
            "title": "30-Day API Call Trend",
            "yAxisName": "Call Count",
            "labels": monthly_keys,
            "values": monthly_values
        })
    }


async def get_celery_data() -> Dict[str, Any]:
    """Celery 页面数据"""
    if _is_dev_mode():
        return _dev_celery()

    now = datetime.now(timezone.utc)
    today_str = now.date().isoformat()
    month_str = now.strftime("%Y-%m")
    config = EnvConfig.get_config()

    # 队列实时数据
    queue = ServiceMetrics.get_celery_queue_stats(config)
    if not queue:
        queue = {
            'pending': -1, 'ready': -1, 'unacknowledged': -1,
            'consumers': -1, 'utilisation': -1,
            'published': -1, 'consumed': -1, 'state': 'unknown',
            'memory': -1, 'message_bytes': -1, 'reductions': -1,
        }

    # 1. 读取 Redis 指标（本月处理数 / 今日处理数 / 今日失败数）
    monthly_key = f"metrics:celery:monthly:{month_str}"
    daily_total_key = f"metrics:celery:daily:total:{today_str}"
    daily_error_key = f"metrics:celery:daily:error:{today_str}"

    pipe_result = await RedisClient.get_by_pipe([monthly_key, daily_total_key, daily_error_key])
    if pipe_result['code'] == 1000:
        monthly_processed, daily_processed, today_failed = pipe_result['data']
    else:
        monthly_processed, daily_processed, today_failed = 0, 0, 0

    # 2. 30天 Celery 消费趋势
    celery_keys, celery_values = await ServiceMetrics.get_monthly_celery_stats(now)

    # 3. 30天 Celery 失败任务趋势
    error_keys, error_values = await ServiceMetrics.get_monthly_celery_error_stats(now)

    return {
        "cards": [
            {
                "title": "Monthly Processed",
                "value": f"{monthly_processed:,}",
                "icon": "📊",
                "color": "#f59e0b"
            },
            {
                "title": "Today's Processed",
                "value": f"{daily_processed:,}",
                "icon": "📡",
                "color": "#667eea"
            },
            {
                "title": "Pending Tasks",
                "value": f"{queue['pending']:,}",
                "icon": "📦",
                "color": "#4facfe"
            },
            {
                "title": "Consumers",
                "value": f"{queue['consumers']:,}",
                "icon": "🔗",
                "color": "#43e97b"
            },
            {
                "title": "Today's Failed",
                "value": f"{today_failed:,}",
                "icon": "❌",
                "color": "#fa709a"
            },
        ],
        "celery_chart_json": json.dumps({
            "title": "30-Day Celery Task Consumption",
            "yAxisName": "Tasks",
            "labels": celery_keys,
            "values": celery_values
        }),
        "celery_error_chart_json": json.dumps({
            "title": "30-Day Celery Failed Tasks",
            "yAxisName": "Failed Tasks",
            "labels": error_keys,
            "values": error_values
        })
    }


async def get_game_api_data() -> Dict[str, Any]:
    """Game API 页面数据"""
    if _is_dev_mode():
        return _dev_game_api()

    now = datetime.now(timezone.utc)
    today_str = now.date().isoformat()
    month_str = now.strftime("%Y-%m")

    # 1. 读取指标卡片数据（本月总计 / 今日总计 / 今日失败）
    monthly_key = f"metrics:http:monthly:{month_str}"
    daily_total_key = f"metrics:http:daily:total:{today_str}"
    daily_error_key = f"metrics:http:daily:error:{today_str}"

    pipe_result = await RedisClient.get_by_pipe([monthly_key, daily_total_key, daily_error_key])
    if pipe_result['code'] == 1000:
        monthly_total, daily_total, daily_error = pipe_result['data']
    else:
        monthly_total, daily_total, daily_error = 0, 0, 0

    # 计算失败率
    if daily_total > 0:
        failure_rate = round(daily_error / daily_total * 100, 2)
        failure_rate_str = f"{failure_rate}%"
    else:
        failure_rate_str = "0%"

    # 2. 获取30天图表数据
    monthly_keys, total_values, error_values = await ServiceMetrics.get_monthly_http_stats(now)

    # 计算每日错误率
    error_rate_values = []
    for t, e in zip(total_values, error_values):
        if e == 0 or t == 0:
            error_rate_values.append(0)
        else:
            error_rate_values.append(round(e / t * 100, 2))

    return {
        "cards": [
            {
                "title": "Monthly Requests",
                "value": f"{monthly_total:,}",
                "icon": "📊",
                "color": "#f59e0b"
            },
            {
                "title": "Today's Requests",
                "value": f"{daily_total:,}",
                "icon": "📡",
                "color": "#667eea"
            },
            {
                "title": "Today's Failed",
                "value": f"{daily_error:,}",
                "icon": "⚠️",
                "color": "#fa709a"
            },
            {
                "title": "Failure Rate",
                "value": failure_rate_str,
                "icon": "❌",
                "color": "#ef4444"
            },
            {
                "title": "Reserved",
                "value": "--",
                "icon": "📋",
                "color": "#4facfe"
            },
        ],
        "http_total_chart_json": json.dumps({
            "title": "30-Day API Call Volume",
            "yAxisName": "Requests",
            "labels": monthly_keys,
            "values": total_values
        }),
        "http_error_rate_chart_json": json.dumps({
            "title": "30-Day API Error Rate",
            "yAxisName": "Error Rate (%)",
            "labels": monthly_keys,
            "values": error_rate_values
        })
    }


async def get_user_activity_data() -> Dict[str, Any]:
    """User Activity 页面数据"""
    if _is_dev_mode():
        return _dev_user_activity()

    REFRESH_LABELS = {
        'overdue': 'Overdue',
        'within_24h': 'Within 24h',
        'within_week': 'Within Week',
        'within_month': 'Within Month',
        'within_quarter': 'Within Quarter',
    }

    # 用户等级分布
    # 临时固定为 0：数据源 T_table_meta 的 base_users / recent_lv1 / recent_lv2 已停写
    level_legend = ['None', 'Standard', 'Plus']
    level_data = [
        {'name': 'None', 'value': 0},
        {'name': 'Standard', 'value': 0},
        {'name': 'Plus', 'value': 0}
    ]

    # 刷新计划分布（合并 user + clan）
    refresh_resp = await PlatformModel.read_user_refresh_stats()
    refresh_legend = []
    refresh_data = []
    if refresh_resp['code'] == 1000:
        for status, uc, cc in refresh_resp['data']:
            label = REFRESH_LABELS.get(status, status)
            refresh_legend.append(label)
            refresh_data.append({'name': label, 'value': uc + cc})

    # 活跃度分布 (0-9)
    activity_resp = await PlatformModel.read_user_activity_distribution()
    activity_labels = []
    activity_values = []
    if activity_resp['code'] == 1000:
        for lv, cnt in activity_resp['data']:
            activity_labels.append(str(lv))
            activity_values.append(cnt)

    # 24h 刷新计划分布（user + clan 堆叠）
    hourly_resp = await PlatformModel.read_user_refresh_hourly_stats()
    hourly_labels = []
    hourly_users = []
    hourly_clans = []
    if hourly_resp['code'] == 1000:
        for hour, pu, pc in hourly_resp['data']:
            hourly_labels.append(f'H{hour}')
            hourly_users.append(pu)
            hourly_clans.append(pc)

    return {
        # 临时固定为 0：数据源 T_table_meta 的 planned_users / planned_clans 已停写
        "planned_users": 0,
        "planned_clans": 0,
        "user_level_chart_json": json.dumps({
            "title": "User Level Distribution",
            "legend": level_legend,
            "data": level_data,
        }),
        "refresh_plan_chart_json": json.dumps({
            "title": "Refresh Plan Distribution",
            "legend": refresh_legend,
            "data": refresh_data,
        }),
        "activity_chart_json": json.dumps({
            "title": "User Activity Distribution",
            "yAxisName": "Users",
            "labels": activity_labels,
            "values": activity_values,
        }),
        "hourly_chart_json": json.dumps({
            "title": "24-Hour Scheduled Refresh",
            "yAxisName": "Planned Count",
            "labels": hourly_labels,
            "user_values": hourly_users,
            "clan_values": hourly_clans,
        }),
    }


def _parse_error_line(line: str) -> dict | None:
    """解析单行错误日志: HH:MM:SS,Source,ErrorType,UUID"""
    line = line.strip()
    if not line:
        return None
    parts = line.split(",", 3)
    if len(parts) < 4:
        return None
    return {
        "time": parts[0],
        "source": parts[1],
        "error_type": parts[2],
        "uuid": parts[3],
    }


def get_error_logs_data(today, log_dir, page: int = 1, per_page: int = 20, uuid_filter: str = "") -> dict:
    """读取今日错误日志，支持分页和 UUID 精确查找"""
    file = log_dir / f"error/{today.isoformat()}.log"
    entries = []

    if file.exists():
        with open(file, "r", encoding="utf-8") as f:
            for line in f:
                parsed = _parse_error_line(line)
                if parsed:
                    entries.append(parsed)

    # 按来源统计（UUID 过滤前，始终反映全天全量数据）
    api_errors = 0
    celery_errors = 0
    other_errors = 0
    for e in entries:
        src = e["source"].upper()
        if src == "API":
            api_errors += 1
        elif src == "CELERY":
            celery_errors += 1
        else:
            other_errors += 1

    # UUID 过滤
    if uuid_filter:
        entries = [e for e in entries if e["uuid"] == uuid_filter]

    # 按时间倒序
    entries.sort(key=lambda e: e["time"], reverse=True)

    total = len(entries)
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_entries = entries[start:start + per_page]

    return {
        "entries": page_entries,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "uuid_filter": uuid_filter,
        "api_errors": api_errors,
        "celery_errors": celery_errors,
        "other_errors": other_errors,
    }


def get_exception_detail(uuid: str, log_dir) -> str | None:
    """读取 UUID 对应的详细异常日志"""
    file = log_dir / f"exception/{uuid}.log"
    if file.exists():
        with open(file, "r", encoding="utf-8") as f:
            return f.read()
    return None