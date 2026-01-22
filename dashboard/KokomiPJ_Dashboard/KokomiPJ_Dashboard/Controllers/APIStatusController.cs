

namespace KokomiPJ_Dashboard.Controllers;

/// <summary>
/// API运行情况控制器
/// </summary>
public class APIStatusController : Controller
{
    private readonly ILogger<HomeController> _logger;

    public APIStatusController(ILogger<HomeController> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// API运行情况
    /// </summary>
    /// <returns></returns>
    public async Task<IActionResult> ReqStats()
    {
        return View();
    }

   
}
