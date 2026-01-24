
namespace KokomiPJ_Dashboard_BLL.Models.Dtos.KokomiAPI;


#region KokomiAPI返回值模型区

/// <summary>
/// KokomiAPI 统一返回壳模型
/// </summary>
/// <typeparam name="T">data 的实际类型</typeparam>
public sealed class ApiEnvelopeRaw<T>
{
    /// <summary>
    /// 状态（如 "success"）
    /// </summary>
    [JsonProperty("status")]
    public string? Status { get; set; }

    /// <summary>
    /// code（如 200）
    /// </summary>
    [JsonProperty("code")]
    public int Code { get; set; }

    /// <summary>
    /// 信息（如 "success"）
    /// </summary>
    [JsonProperty("message")]
    public string? Message { get; set; }

    /// <summary>
    /// 返回数据
    /// </summary>
    [JsonProperty("data")]
    public T? Data { get; set; }
}

/// <summary>
/// API状态接口 data 节点返回值
/// </summary>
public sealed class ApiStatusDataRaw
{
    /// <summary>
    /// 页码（示例： "APIStatus /ReqStats"）
    /// </summary>
    [JsonProperty("page")]
    public string? Page { get; set; }

    /// <summary>
    /// 时区（示例： "UTC"）
    /// </summary>
    [JsonProperty("timezone")]
    public string? Timezone { get; set; }

    private long _timestamp;

    /// <summary>
    /// 时间戳
    /// </summary>
    [JsonProperty("timeatamp")]
    public long Timestamp
    {
        get => _timestamp;
        set => _timestamp = value;
    }

    /// <summary>
    /// 统计数据
    /// </summary>
    [JsonProperty("metrics")]
    public ApiStatusMetricsRaw? Metrics { get; set; }
}

/// <summary>
/// metrics 节点：API运行状况模型
/// </summary>
public sealed class ApiStatusMetricsRaw
{
    /// <summary>
    /// 今日数据
    /// </summary>
    [JsonProperty("today")]
    public TodayMetricsRaw? Today { get; set; }

    /// <summary>
    /// 今日请求状况
    /// </summary>
    [JsonProperty("api_request_today")]
    public ChartBlockRaw? ApiRequestToday { get; set; }

    /// <summary>
    /// 最近30日请求数据
    /// </summary>
    [JsonProperty("api_request_30d")]
    public ChartBlockRaw? ApiRequest30d { get; set; }

    /// <summary>
    /// 最近30日 Celery 任务数（看你接口命名推断）
    /// </summary>
    [JsonProperty("celery_tasks_30d")]
    public ChartBlockRaw? CeleryTasks30d { get; set; }

    /// <summary>
    /// 最近14天请求情况
    /// </summary>
    [JsonProperty("api_calls_14d")]
    public ChartBlockRaw? ApiCalls14d { get; set; }

    /// <summary>
    /// 最近14天请求失败率情况
    /// </summary>
    [JsonProperty("api_failed_rate_14d")]
    public ChartBlockRaw? ApiFailedRate14d { get; set; }
}

/// <summary>
/// 今日统计数据
/// </summary>
public sealed class TodayMetricsRaw
{
    /// <summary>
    /// 请求总量
    /// </summary>
    [JsonProperty("requests")]
    public int Requests { get; set; }

    /// <summary>
    /// 请求错误量
    /// </summary>
    [JsonProperty("errors")]
    public int Errors { get; set; }

    /// <summary>
    /// 请求耗时（毫秒）
    /// </summary>
    [JsonProperty("elapsed_ms")]
    public int ElapsedMs { get; set; }

    /// <summary>
    /// 请求 API 统计次数
    /// </summary>
    [JsonProperty("api_counts")]
    public int ApiCounts { get; set; }

    /// <summary>
    /// 请求失败次数
    /// </summary>
    [JsonProperty("failed_counts")]
    public int FailedCounts { get; set; }
}

/// <summary>
/// 图表数据块（ECharts/AntV 之类可直接消费）
/// </summary>
public sealed class ChartBlockRaw
{
    /// <summary>
    /// X 轴键（日期/小时等）
    /// </summary>
    [JsonProperty("keys")]
    public List<string> Keys { get; set; } = [];

    /// <summary>
    /// series 列表（多条曲线/柱状等）
    /// </summary>
    [JsonProperty("series")]
    public List<ChartSeriesRaw> Series { get; set; } = [];
}

/// <summary>
/// 图表系列（ECharts series）
/// </summary>
public sealed class ChartSeriesRaw
{
    /// <summary>
    /// 值名称（legend）
    /// </summary>
    [JsonProperty("name")]
    public string? Name { get; set; }

    /// <summary>
    /// 值类型（line/bar 等）
    /// </summary>
    [JsonProperty("type")]
    public string? Type { get; set; }

    /// <summary>
    /// Y 轴数据
    /// null/小数/整数都可能出现，用 double? 最稳
    /// </summary>
    [JsonProperty("data")]
    public List<double?> Data { get; set; } = [];
}

#endregion

