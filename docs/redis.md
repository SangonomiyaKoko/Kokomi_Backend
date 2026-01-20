# Redis Key 说明

```txt
├── bot_bind       # 用户绑定数据的缓存
├── status         # 用于标识子服务是否正常运行
├── user_refresh   # 用户刷新中去重和防卡死
├── metrics        # 记录运行中的请求量和错误量
├── token          # 记录用户通过的授权字符串
```