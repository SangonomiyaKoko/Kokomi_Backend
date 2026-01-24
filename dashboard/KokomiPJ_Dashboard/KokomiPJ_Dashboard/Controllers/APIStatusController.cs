using Newtonsoft.Json;

namespace KokomiPJ_Dashboard.Controllers;

/// <summary>
/// API运行情况控制器
/// </summary>
public class APIStatusController : Controller
{
    #region 私有字段

    private readonly ILogger<HomeController> _logger;

    //API运行状况页面业务逻辑BLL
    private readonly IAPIStatusBLL _apiStatusBLL;

    #endregion



    #region 构造函数

    public APIStatusController(ILogger<HomeController> logger, 
        IAPIStatusBLL apiStatusBLL)
    {
        _logger = logger;
        _apiStatusBLL = apiStatusBLL;
    }

    #endregion


    #region 页面

    /// <summary>
    /// API运行情况页面
    /// </summary>
    /// <returns></returns>
    public async Task<IActionResult> ReqStats()
    {
        var apiData = await _apiStatusBLL.GetApiStatusAsync();
        ViewBag.apiData = JsonConvert.SerializeObject(apiData);
        return View();
    }

    #endregion



}
