# Kokomi_API Project

本项目主要用于实现对不同类型游戏 API 接口返回数据处理和封装，返回标准化后的数据

## 核心架构设计

由于游戏 API 存在较高的跨地域请求延迟，本项目采用了分布式地区部署方案

- 完整服务由 1 台主节点和 5 台子节点组成，子节点汇总必要数据发送给主节点
- 子节点的物理地址分别位于`亚洲` `欧洲` `北美` `俄罗斯` `中国`，以对应游戏的 5 个区服
- 各子节点仅负责请求并处理所属地区的数据，避免跨区请求以保证效率
- 各子节点对原始 API 数据进行处理或者储存，返回经过处理后的标准化数据
- 各子节点均不对外暴露，仅允许主节点 和 Root 用户进行远程访问

## 项目文件结构

```
project/
├── app/          # API 服务
├── data/         # 项目运行所需数据
├── docs/         # 相关文档
├── init/         # 项目初始化文件
├── logs/         # 日志数据
├── scripts/      # 子服务
├── task/         # 消息队列消费者
├── tests/        # 相关测试脚本
└── tools/        # 相关小工具脚本
```

## 内部服务说明

```
app/:             API 服务 + Dashboard 服务
task/:            Celery 消费者，消费 MQ 中待更新的用户
scripts/account/: 读取需要更新的用户 ID，发送到 MQ
scripts/cache/:   更新用户随机缓存数据，实现船只排行榜
scripts/member/:  更新工会内的用户列表
scripts/stats/:   遍历所有缓存数据，统计服务器数据
recent/:          记录用户近期数据
season/:          记录工会赛季信息，实现工会排行榜
```

## 项目依赖

```
# 生产环境下的必要模块：
#     API本体：fastapi uvicorn jinja2
#     ENV加载：python-dotenv
#     网络请求：httpx requests
#     数据库：aiomysql dbutils
#     中间件：redis celery
#     进度条：tqdm
#     
# 
# 开发环境下的额外模块
#     汉化支持：polib
#     数据导出: openpyxl
```

## 部署步骤

### 部署前提

1. 确保 Python >= 3.10
2. 部署在本地的 MySQL + Redis + RabbitMQ

### 拉取代码

```bash
# 检查git
git --version

# 拉取代码
git clone https://github.com/SangonomiyaKoko/Kokomi_Backend.git

# 进入项目文件夹
cd Kokomi_Backend

# 拉取最新代码
git pull origin main

# 丢弃修改（如需）
git restore .
git reset --hard  # 旧版
```

### 虚拟环境配置

本项目采用虚拟环境管理配置，推荐不要直接安装包到本地环境中

```bash
# [Linux] 更新系统包索引并安装必要组件
sudo apt update
sudo apt install -y python3-pip python3.12-venv  # 这里是3.12，请根据实际版本修改

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
.venv/Scripts/activate    # windows
source .venv/bin/activate # linux

# 在虚拟环境中安装所需依赖
pip install -r requirements.txt      # 生产环境
pip install -r requirements-dev.txt  # 开发环境
```

## 项目初始化

请根据实际环境，来选择对应的部署流程

1. 生产环境： [查看详细文档](docs/deploy/prod.md)
2. 开发环境（完整）： [查看详细文档](docs/deploy/dev-full.md)
3. 开发环境（受限）： [查看详细文档](docs/deploy/dev-restrict.md)