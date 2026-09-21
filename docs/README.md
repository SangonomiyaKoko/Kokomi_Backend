# 文档索引

本目录按**四类职责**组织，每类各占一个子树，新增文档时按下表归位。

| # | 目录 | 职责 | 语言 |
| --- | --- | --- | --- |
| 一 | [deploy/](deploy/) | 部署步骤 | 仅中文 |
| 二 | [api/](api/) | 接口返回值、返回代码含义等对外关键文档 | **中英各一份** |
| 三 | [services/](services/) | 服务设计文档 | 仅中文 |
| 四 | [core/](core/) | 系统核心设计 | 仅中文 |

---

## 一、部署步骤

| 文档 | 说明 |
| --- | --- |
| [docker.md](deploy/docker.md) | Docker 安装 |
| [prod.md](deploy/prod.md) | 生产环境部署步骤 |
| [dev-full.md](deploy/dev-full.md) | 开发环境（完整模式）部署步骤 |
| [dev-restrict.md](deploy/dev-restrict.md) | 开发环境（受限模式）部署步骤 |

## 二、接口文档

对外暴露的关键文档，**中英各一份**，两种语言的目录结构一一对应。`return.md` 的英文版链接通过
`app/main.py` 的 `app_description` 对外公开，改动文件名或路径时需同步更新该处。

| 中文 | 英文 | 说明 |
| --- | --- | --- |
| [cn/return.md](api/cn/return.md) | [en/return.md](api/en/return.md) | API 返回值说明 |
| [cn/code.md](api/cn/code.md) | [en/code.md](api/en/code.md) | 业务错误状态码 |

## 三、服务设计文档

命名规则：**取服务目录路径，把 `/` 换成 `_`**，例如 `scripts/cache/` → `scripts_cache.md`。

| 文档 | 服务 |
| --- | --- |
| [season.md](services/season.md) | `season/` 公会赛季信息与排行榜 |
| [tasks.md](services/tasks.md) | `tasks/` Celery 用户数据刷新（消费 `refresh_queue`） |

## 四、系统核心设计

跨服务的核心机制设计，不属于任何单个服务。

| 文档 | 说明 |
| --- | --- |
| [activity.md](core/activity.md) | 用户活跃等级系统 |
