namespace KokomiPJ_Dashboard;

/// <summary>
/// 程序启动入口
/// </summary>
public class Program
{
    public static void Main(string[] args)
    {
        var builder = WebApplication.CreateBuilder(args);

        // Add services to the container.
        var mvc = builder.Services.AddControllersWithViews();
        //增加启用Razor页面热更新
        if (builder.Environment.IsDevelopment())
        {
            mvc.AddRazorRuntimeCompilation();
        }

        //往DI容器内注入HttpclientFactory
        builder.Services.AddHttpClient();

        //读取Appsetting.json中的API选项相关作为
        builder.Services.Configure<KokomiAPIOptions>(
        builder.Configuration.GetSection("KokomiAPIOptions"));

        //为API请求业务注入HttpClient
        builder.Services.AddHttpClient<IAPIStatusBLL, APIStatusBLL>((sp, client) =>
        {
            var opt = sp.GetRequiredService
            <Microsoft.Extensions.Options.IOptions<KokomiAPIOptions>>().Value;

            if (!string.IsNullOrWhiteSpace(opt.BaseUrl))
                client.BaseAddress = new Uri(opt.BaseUrl);

            client.Timeout = TimeSpan.FromSeconds(10);
        });

        var app = builder.Build();

       

        // Configure the HTTP request pipeline.
        if (!app.Environment.IsDevelopment())
        {
            app.UseExceptionHandler("/Home/Error");
        }
        app.UseStaticFiles();

        app.UseRouting();

        app.UseAuthorization();
        //默认启动时指向Home/Index
        app.MapControllerRoute(
            name: "default",
            pattern: "{controller=Home}/{action=Index}/{id?}");

        app.Run();
    }
}
