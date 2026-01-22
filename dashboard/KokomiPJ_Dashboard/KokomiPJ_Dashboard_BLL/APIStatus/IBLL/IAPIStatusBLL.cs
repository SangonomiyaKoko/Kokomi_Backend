using KokomiPJ_Dashboard_BLL.Models.Dtos.KokomiAPI;

namespace KokomiPJ_Dashboard_BLL.APIStatus.IBLL;

/// <summary>
/// API运行情况BLL
/// </summary>
public interface IAPIStatusBLL
{
    /// <summary>
    /// 请求Kokomi的API返回状态
    /// </summary>
    /// <param name="ct"></param>
    /// <returns>返回API工作状态DTO</returns>
    Task<ApiEnvelopeRaw<ApiStatusDataRaw>> GetApiStatusAsync(CancellationToken ct = default);
}
