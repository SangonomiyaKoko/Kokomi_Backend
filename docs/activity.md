# 用户活跃等级系统设计文档

Activity_Level 是标识用户活跃度的重要数据，主要用于计算用户数据的刷新间隔

## 活跃等级对应关系

Activity_Level 主要由以下三个数据决定

1. is_public: 是否公开战绩
2. total_battles: 是否有战斗数据
3. last_battle_time: 最后战斗时间

> 对应表格如下，其中+越多表示越活跃

| is_public | total_battles | last_battle_time | activity_level | decsribe |
| --------- | ------------- | ---------------- | -------------- | -------- |
| 1         | 0             | 0                | 0              | NoData   |
| 1         | -             | [0, 1d]          | 1              | +++++++  |
| 1         | -             | [1d, 3d]         | 2              | ++++++   |
| 1         | -             | [3d, 7d]         | 3              | +++++    |
| 1         | -             | [7d, 1m]         | 4              | ++++     |
| 1         | -             | [1m, 3m]         | 5              | +++      |
| 1         | -             | [3m, 6m]         | 6              | ++       |
| 1         | -             | [6m, 1y]         | 7              | +        |
| 1         | -             | [1y, + ]         | 8              | -        |

## 用户等级对应刷新间隔

| activity_level | normal_user | recent_user | recents_user |
| -------------- | ----------- | ----------- | ------------ |
| 0              | 30d         | \           | \            |
| 1              | 1d          | 1h          | 10m          |
| 2              | 2d          | 2h          | 20m          |
| 3              | 3d          | 3h          | 25m          |
| 4              | 5d          | 4h          | 30m          |
| 5              | 7d          | 6h          | 60m          |
| 6              | 15d         | 8h          | \            |
| 7              | 20d         | 12h         | \            |
| 8              | 30d         | \           | \            |

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

