# 用户活跃等级文档

Activity_Level 是标识用户活跃度的重要数据，主要用于计算用户数据的刷新间隔

## 活跃等级对应关系

Activity_Level 主要由以下三个数据决定

1. is_public: 是否公开战绩
2. total_battles: 是否有战斗数据
3. last_battle_time: 最后战斗时间

> 对应表格如下，其中+越多表示越活跃

| is_public | total_battles | last_battle_time | activity_level | decsribe |
| --------- | ------------- | ---------------- | -------------- | -------- |
| 0         | -             | -                | 0              | Hidden   |
| 1         | 0             | 0                | 1              | NoData   |
| 1         | -             | [0, 1d]          | 2              | +++++++  |
| 1         | -             | [1d, 3d]         | 3              | ++++++   |
| 1         | -             | [3d, 7d]         | 4              | +++++    |
| 1         | -             | [7d, 1m]         | 5              | ++++     |
| 1         | -             | [1m, 3m]         | 6              | +++      |
| 1         | -             | [3m, 6m]         | 7              | ++       |
| 1         | -             | [6m, 1y]         | 8              | +        |
| 1         | -             | [1y, + ]         | 9              | -        |

## 用户等级对应刷新间隔

| activity_level | normal_user | recent_user | recents_user |
| -------------- | ----------- | ----------- | ------------ |
| 0              | 5d          | 6h          | \            |
| 1              | 25d         | \           | \            |
| 2              | 1d          | 30m         | 20m          |
| 3              | 2d          | 1h          | 20m          |
| 4              | 3d          | 2h          | 25m          |
| 5              | 5d          | 3h          | 30m          |
| 6              | 7d          | 4h          | 60m          |
| 7              | 15d         | 5h          | \            |
| 8              | 20d         | 6h          | \            |
| 9              | 30d         | \           | \            |

## 用户不存在和用户无数据的区别

通过 vortex 请求用户数据时，会有一下几种返回值

### 正常返回值

可以正常获取到用户的基本信息

```json
{
  "status": "ok",
  "data": {
    "2023619511": {
      "statistics": {
        "......": {}
      },
      "name": "username",
      "created_at": 123456789,
      "activated_at": 123456789,
      "visibility_settings": false,
      "dog_tag": {
        "......": 123456789
      }
    }
  }
}
```

### 隐藏战绩

标志是有一个 hidden_profile 的 key

```json
{
  "status": "ok",
  "data": {
    "211817574": {
      "name": "username",
      "hidden_profile": true
    }
  }
}
```

### 用户不存在

标志是 code 404，可能是由于 uid 对应的用户不存在或者输入的 uid 格式错误

```json
{
  "status": "error",
  "error": "Not Found"
}
```

### 用户数据不存在

这种通常表示该用户注册后没有进行游戏，所以没数据，但是存在用户名称

> WG 服

```json
{
  "status": "ok",
  "data": {
    "3011597408": {
      "statistics": {
        "mastery_sign": "No_Sign"
      },
      "name": "Player_6926239937",
      "created_at": 1767098220.0,
      "activated_at": 1767098262.0,
      "visibility_settings": false
    }
  }
}
```

> Lesta 服

```json
{
  "status": "ok",
  "data": {
    "211817573": {
      "statistics": {},
      "name": "Player_2107715321",
      "created_at": 1698418907.0,
      "activated_at": 1698418907.0,
      "visibility_settings": false
    }
  }
}
```

## 具体代码处理

### 1. 请求返回

```python
res = await client.get(url=url)
requset_code = res.status_code
requset_result = res.json()
if requset_code == 404:
    # 用户不存在或者账号删除的情况，返回None
    return None
elif requset_code == 200:
    # 正常返回值的处理, 返回data内数据
    return requset_result['data']
else:
    res.raise_for_status()  # 其他状态码，抛出异常
```

### 2. 初步处理

```python
if response:
    user_basic = response[str(account_id)]
if user_basic == None:
    # 用户数据不存在则返回
    return 'UserNotExist'
```

## RecentPro 功能说明

RecentPro是在Recent功能的基础上，提供:

1. 更大的数据储存空间 (600天)
2. 过去24h内的详细战斗数据 (原Recents功能)

Premium身份会绑定你的平台ID(例如QQ号)，默认提供3个可用名额，可用于启用 RecentPro 功能的游戏账号，例如:

```txt
1. (已使用) SangonomiyaKokomi_
2. (已使用) Kokomi_My_wife
3. (未使用) /
```
> 启用名额不会消耗，只会被占用。删除已启用的游戏账号后，该名额将可再次使用

### 订阅价格

| 订阅类型 | 时长    | 价格 |
| ---- | ----- | -------- |
| 包月   | 1 个月  | /      |
| 包季   | 3 个月  | /      |
| 包年   | 12 个月 | ¥50     |

