
namespace KokomiPJ_Dashboard_BLL.Models;

/// <summary>
/// ApiStatus 客户端配置
/// </summary>
public sealed class  KokomiAPIOptions
{
    /// <summary>
    /// 是否使用 Mock（true：读本地 json；false：请求真实接口）
    /// </summary>
    public bool UseMock { get; set; } = true;

    /// <summary>
    /// Mock JSON 文件路径（相对 ContentRoot 或输出目录）
    /// 例如：Mocks/response.json
    /// </summary>
    public string MockJsonPath { get; set; } = "Mocks/response.json";

    /// <summary>
    /// 真实 API BaseUrl（例如：https://your-api-host）
    /// </summary>
    public string BaseUrl { get; set; } = "";

    /// <summary>
    /// 真实 API Endpoint（例如：/APIStatus/ReqStats）
    /// </summary>
    public string Endpoint { get; set; } = "/APIStatus/ReqStats";
}
