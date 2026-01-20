# API 返回值说明

> 本文档说明接口返回的 `status`、`code`、`message`、`data` 的含义，按状态分类并提供可查表的形式。

---

## 一、通用返回结构

```json
{
  "status": "ok",        // 或 "error"
  "code": 1000,
  "message": "success",
  "data": null
}
```

| 字段名     | 类型            | 说明                        |
| ------- | ------------- | ------------------------- |
| status  | string        | `"ok"` 或 `"error"`，标记响应类型 |
| code    | int           | 状态码，含义依赖 `status`         |
| message | string        | 描述信息（成功/失败/异常）            |
| data    | object / null | 返回数据或错误详情                 |

---

## 二、状态码表（按 status 分类）

### 1️⃣ Status = `"ok"` （业务正常响应）

> code = 1000 → 成功获取数据 / 操作成功

> code ≠ 1000 → 未成功获取到数据，具体原因查看 `code` 和 `messaeg`

| Code范围  | 含义            | 备注            |
| --------- | ------------- | ------------- |
| 1000      | 成功获取数据 / 操作成功 | 如果表示操作成功，则 `data` 为 `null` 值 |
| 2000-2999 | 业务层消息 | * |
| 3000-3999 | 外部接口消息 | 主要用于请求外部接口 |


**示例：业务成功**

```json
{
  "status": "ok",
  "code": 1000,
  "message": "Success",
  "data": null
}
```

**示例：业务失败**

```json
{
  "status": "ok",
  "code": 1234,
  "message": "UserNotExist",
  "data": null
}
```

---

### 2️⃣ Status = `"error"` （系统捕获到异常）

> 表示程序内部或系统异常

> code 与 message 说明异常原因，data 包含错误详情

| Code | 含义     | 备注                 |
| ---- | ------ | ------------------ |
| 4001 | 内部服务异常 | data 可包含异常堆栈       |

**示例：系统异常**

```json
{
  "status": "error",
  "code": 3001,
  "message": "internal server error",
  "data": {
    "exception": "ValueError: invalid value"
  }
}
```