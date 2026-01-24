using KokomiPJ_Dashboard_BLL.APIStatus.IBLL;
using KokomiPJ_Dashboard_BLL.Models.Dtos.KokomiAPI;


namespace KokomiPJ_Dashboard_BLL.APIStatus.BLL;

/// <summary>
/// API请求业务类
/// </summary>
public class APIStatusBLL:DBServiceBase,IAPIStatusBLL
{
    #region 私有属性

    //Httpclient
    private readonly HttpClient _httpClient;

    //Appsetting.json内的API相关信息
    private readonly KokomiAPIOptions _opt;

    // 注入 IHostEnvironment 来定位 ContentRoot
    private readonly Microsoft.Extensions.Hosting.IHostEnvironment? _env;

    #endregion

    #region 构造方法
    public APIStatusBLL(
       HttpClient httpClient,
       IOptions<KokomiAPIOptions> opt,
       Microsoft.Extensions.Hosting.IHostEnvironment? env = null)
    {
        _httpClient = httpClient;
        _opt = opt.Value;
        _env = env;
    }
    #endregion
    
    #region 请求API工作状态

    // </inhertidoc>
    public async Task<ApiEnvelopeRaw<ApiStatusDataRaw>> GetApiStatusAsync(CancellationToken ct = default)
    {
        if (_opt.UseMock)
        {
            return await LoadFromMockJsonAsync(ct);
        }

        // ✅ 保留真实请求代码
        return await RequestRealApiAsync(ct);
    }

    #endregion

    #region Private Methods

    /// <summary>
    /// 从项目 Mock JSON 文件读取并反序列化（测试阶段）
    /// </summary>
    private async Task<ApiEnvelopeRaw<ApiStatusDataRaw>> LoadFromMockJsonAsync(CancellationToken ct)
    {
        // 优先用 ContentRoot（在 Web 项目里更准）
        var baseDir = _env?.ContentRootPath ?? AppContext.BaseDirectory;
        var fullPath = Path.Combine(baseDir, _opt.MockJsonPath);

        if (!File.Exists(fullPath))
        {
            return new ApiEnvelopeRaw<ApiStatusDataRaw>
            {
                Status = "error",
                Code = -1,
                Message = $"Mock JSON not found: {fullPath}",
                Data = null
            };
        }

        var json = await File.ReadAllTextAsync(fullPath, ct);

        var dto = JsonConvert.DeserializeObject<ApiEnvelopeRaw<ApiStatusDataRaw>>(json);

        return dto ?? new ApiEnvelopeRaw<ApiStatusDataRaw>
        {
            Status = "error",
            Code = -1,
            Message = "Mock JSON deserialize failed",
            Data = null
        };
    }

    /// <summary>
    /// 请求真实 API 并反序列化（联调/上线阶段）
    /// </summary>
    private async Task<ApiEnvelopeRaw<ApiStatusDataRaw>> RequestRealApiAsync(CancellationToken ct)
    {
        var json = await _httpClient.GetStringAsync(_opt.BaseUrl+ "status/?page=api", ct);

        var dto = JsonConvert.DeserializeObject<ApiEnvelopeRaw<ApiStatusDataRaw>>(json);

        return dto ?? new ApiEnvelopeRaw<ApiStatusDataRaw>
        {
            Status = "error",
            Code = -1,
            Message = "API returned null",
            Data = null
        };
    }

    #endregion
}
