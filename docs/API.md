# API 参考

Voice Studio 默认在本机 `http://127.0.0.1:8765` 提供管理 API 和 OpenAI 兼容网关。启动后也可以打开 FastAPI 自动生成的交互文档：

- Swagger UI：`http://127.0.0.1:8765/docs`
- OpenAPI JSON：`http://127.0.0.1:8765/openapi.json`

## 鉴权

网关接口使用 Bearer Key：

```http
Authorization: Bearer <Gateway Key>
```

Gateway Key 可在网页的“API 网关”页面查看或轮换。不要把厂商 API Key 放入客户端请求；网关会在本机后端读取系统密钥环或 Docker 环境变量。

## OpenAI 兼容接口

### `GET /v1/models`

返回已配置厂商的模型列表，以及模型支持的操作、克隆能力和流式能力。

### `GET /v1/models/{model_id}`

查询单个模型。`model_id` 可以是完整模型 ID，也可以使用内置别名：

| 别名 | 用途 |
| --- | --- |
| `tts-default` | 默认语音模型 |
| `tts-fast` | 低延迟模型 |
| `tts-hq` | 高质量模型 |

### `POST /v1/audio/speech`

生成完整音频文件。请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | :---: | --- |
| `model` | string | 是 | 模型 ID 或别名 |
| `voice` | string | 是 | 与模型兼容的音色 ID/兼容别名 |
| `input` | string | 是 | 待合成文本，最多 10000 字符 |
| `response_format` | string | 否 | `wav`、`mp3`、`opus`、`aac`、`flac` 或 `pcm`，默认 `mp3` |
| `speed` | number | 否 | `0.25` 到 `4.0`，默认 `1.0` |
| `instructions` | string | 否 | 支持指令控制的模型可使用，最多 2000 字符 |

成功时直接返回音频二进制，并附带 `X-Voice-Studio-Job`、响应格式和延迟等响应头。PCM 是 `s16le` 原始数据，采样率、声道数和位深见 `X-Voice-Studio-PCM-*` 响应头。

### `POST /v1/audio/speech/stream`

通过 Server-Sent Events（SSE）返回音频分片。请求体与上一个接口相同，并可增加：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | ---: | --- |
| `chunk_size` | integer | `8192` | `1024` 到 `65536`，控制兼容分片大小 |

每个事件的 `data` 是 JSON：

| 事件 | 主要字段 | 说明 |
| --- | --- | --- |
| `audio` | `audio`、`index` | `audio` 为 Base64 音频分片 |
| `done` | `job_id`、`provider`、`native_streaming` | 流式生成完成 |
| `error` | `code`、`message` | 生成或上游请求失败 |

示例：

```bash
curl.exe -N "http://127.0.0.1:8765/v1/audio/speech/stream" \
  -H "Authorization: Bearer $VOICE_STUDIO_GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"tts-default","voice":"mimo-default","input":"你好","response_format":"mp3"}'
```

## 错误格式

网关将错误统一为：

```json
{
  "error": {
    "message": "可读错误信息",
    "type": "invalid_request_error",
    "code": "invalid_request"
  }
}
```

常见状态码：

| 状态码 | 含义 |
| ---: | --- |
| `400` | 请求字段、模型、音色或格式无效 |
| `401` | Gateway Key 缺失或错误 |
| `404` | 模型或资源不存在 |
| `409` | 厂商未配置、模型不支持该操作或资源冲突 |
| `502` | 厂商接口或上游音频下载失败 |

## 本地管理 API

网页界面使用 `/api/*` 管理接口完成账号、音色、任务和存储操作。这些接口默认只绑定本机，不是面向公网的独立用户管理 API。部署到局域网或公网前，应增加管理认证、HTTPS 和限流。

主要资源：

| 路径 | 用途 |
| --- | --- |
| `/api/provider-accounts` | 管理厂商账号元数据 |
| `/api/provider-accounts/{account_id}/projects` | 查看、添加或删除火山引擎项目；同一账号可管理多个项目 |
| `/api/provider-accounts/{account_id}/projects/sync` | 使用火山 IAM AK/SK 同步项目列表，并读取各项目已有的语音 API Key；只返回密钥名称、脱敏提示和状态 |
| `/api/provider-accounts/{account_id}/volcengine-slots` | 按指定项目查询可用声音槽位 |
| `/api/models`、`/api/voices` | 读取模型和音色库 |
| `/api/voices/clone`、`/api/voices/design` | 创建克隆或设计音色 |
| `/api/jobs` | 查询、下载、导出和删除任务 |
| `/api/storage` | 读取和更新存储策略 |
| `/api/gateway` | 读取本机网关配置 |
