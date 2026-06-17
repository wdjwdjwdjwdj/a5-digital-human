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

发送文字对话消息，返回 AI 回答。

**请求体（JSON）：**
```json
{
  "query": "西湖有哪些景点？"
}
```

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| query | string | 是 | 用户输入文本 |

**响应示例：**
```json
{
  "reply": "西湖有断桥残雪、苏堤春晓、雷峰夕照、三潭印月等著名景点...",
  "audio": false
}
```

### POST /chat/voice

发送语音对话，支持前端 ASR 文本或服务端 FunASR 识别。

**请求体（multipart/form-data）：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| audio | file | 否 | 用户录音文件（WAV/WebM） |
| text | string | 否 | 前端 ASR 识别的文本（如已有则跳过服务端 ASR） |

**响应示例：**
```json
{
  "reply": "西湖景区免费开放，不设大门票...",
  "audio_url": "/static/audio/abc123.wav",
  "asr_text": "西湖门票多少钱"
}
```

**降级链路：**
1. 优先使用前端 Web Speech API 识别文本
2. 前端无文本时使用服务端 FunASR
3. FunASR 不可用时返回错误提示

### POST /chat/stream

流式对话接口（轮询模式，用于前端打字机效果）。

**请求体（JSON）：**
```json
{
  "query": "推荐一条西湖半日游路线"
}
```

**响应示例：**
```json
{
  "reply": "推荐路线：断桥残雪 → 苏堤春晓 → 花港观鱼 → 雷峰塔..."
}
```

## 对话链路

```
用户输入 → ASR（FunASR / Web Speech） → Dify RAG 检索 → DeepSeek LLM → Edge-TTS → Live2D 口型同步
                                         ↓ 降级                ↓ 降级           ↓ 降级
                                    直连 DeepSeek         通义千问 API     pyttsx3 离线
```
