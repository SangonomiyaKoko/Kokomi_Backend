
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
    /// Mock JSON 文件路径
    /// </summary>
    public string MockJsonPath { get; set; } = "Contents/Mocks/KKMReqMocks/response_1768999593248.json";

    /// <summary>
    /// 真实 API BaseUrl（例如：https://localhost:8000）
    /// </summary>
    public string BaseUrl { get; set; } = "";
}
