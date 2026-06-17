# API 文档

## 健康检查

### GET /health

返回服务健康状态。

**响应示例：**
```json
{
  "status": "ok",
  "env": "development"
}
```

### GET /ping

存活检查。

**响应示例：**
```json
{
  "pong": true
}
```

## 对话

### POST /chat/message

发送对话消息。

**参数：**
| 参数 | 类型 | 说明 |
|------|------|------|
| query | string | 用户输入文本 |

**响应示例：**
```json
{
  "query": "西湖门票多少钱",
  "reply": "西湖景区免费开放，不设大门票..."
}
```
