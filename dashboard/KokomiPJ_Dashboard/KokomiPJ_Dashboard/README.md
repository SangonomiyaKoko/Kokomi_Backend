# KokomiDashboard Project

## 技术栈

- 后端：.NET 8 MVC
- 前端：JavaScript + Vue 3 + Ant Design Vue

## 项目定位

用于 **KokomiPJ** 的后台运维监控（Dashboard / Ops Monitoring）。

## 当前功能

### 1) 导航页
- 路由：`Home/Index`
- 说明：监控入口页面（聚合关键指标/入口导航）

### 2) 后台 API 运行状态统计
- 接口模块：`APIStatus`
- 功能点：请求统计 `ReqStats`

## 路由与模块速查

| 功能 | 页面/模块 | 路由/接口 |
|------|----------|-----------|
| 导航页 | Home | `Home/Index` |
| API 状态统计 | APIStatus | `APIStatus/ReqStats` |

## 计划中

- [ ] 健康检查（Health Check）聚合展示