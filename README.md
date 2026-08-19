# Voice Studio

一个 Windows 本地运行的多厂商语音工作台与 OpenAI 兼容网关 MVP。

当前版本提供通义千问、火山引擎、MiniMax 与 MiMo 真实适配器，覆盖：

- 合成工作台：厂商与模型联动选择、音色、语速、输出格式、试听与下载
- 声音克隆：仅展示支持克隆的模型，保存参考音频并自动切换到所选模型
- Voice Design：通义千问、MiniMax 与 MiMo 的统一文本音色设计界面，支持试听与音色库复用
- 音色库：预置音色、云端音色同步、Voice ID 手工导入、克隆音色管理
- API 网关：GET /v1/models、GET /v1/models/{model_id}、POST /v1/audio/speech、POST /v1/audio/speech/stream
- 网关测试台：模型发现、音频响应、延迟与错误检查，提供 PowerShell、curl、Python、JavaScript 示例
- 网关运行统计：按时间范围与厂商查看请求量、成功率、首片/总耗时 P50/P95、取消次数和错误聚合
- 任务历史：保存原始文字与音频文件，支持按本地日期筛选、展开文字、下载 TXT 与音频
- 真实适配器：Qwen3 TTS、CosyVoice V3、Qwen3 Voice Clone、Seed TTS 2.0、Seed 声音复刻 2.0、MiMo V2.5 TTS 与 VoiceClone

## 模型选择

合成工作台先选择厂商，再选择该厂商支持合成的模型；音色列表会随模型自动过滤。声音克隆页只展示明确标记为支持 `clone` 的模型。

当前内置目录包含：

- 通义千问：Qwen3 TTS Flash、Qwen3 TTS Instruct Flash、Qwen3 TTS VC 2026-01-22、CosyVoice V3 Flash、CosyVoice V3 Plus、Qwen3 TTS VoiceDesign 2026-01-26（真实）
- 火山引擎：Seed TTS 2.0、Seed 声音复刻 2.0（真实）
- MiniMax：Speech 2.8 HD/Turbo、Speech 2.6 HD/Turbo（真实）
- 小米 MiMo：MiMo V2.5 TTS、VoiceClone、VoiceDesign（真实接口目录）

Qwen3 TTS 与声音复刻模型依据千问官方文档接入；模型可用性仍以厂商控制台和账号权限为准。所有未接入真实适配器的模型都在界面中明确标为“演示”。

## Voice Design

左侧“Voice Design”页面提供三家厂商的统一入口：

- 通义千问：通过 `qwen-voice-design` 为 `qwen3-tts-vd-2026-01-26` 创建音色，保存厂商返回的 Voice ID 与 WAV 试听音频。
- MiniMax：调用 `/v1/voice_design`，使用返回的 `voice_id` 和十六进制试听音频，创建后保存为可复用音色。
- 小米 MiMo：调用 `mimo-v2.5-tts-voicedesign`，保存描述模板和试听文件；MiMo 没有持久化 Voice ID，后续每次合成都会把模板描述作为 `user` 消息发送。

设计音色会进入“音色库”，类型显示为“设计”。创建成功后，页面会自动将其设为合成工作台的当前模型和音色；MiMo 设计音色仍属于请求级资产，不会伪装成云端 Voice ID。

## 启动

在 PowerShell 中运行：

    cd E:\Projects\voice-studio
    .\start.ps1

首次运行会创建 backend\.venv、安装依赖、构建前端并启动服务。管理界面地址：

http://127.0.0.1:8765

## OpenAI 兼容调用

首次启动会自动生成本地网关 Key，并保存到 `data/gateway.json`。在左侧“API 网关”页面可以查看、复制或轮换 Key。生产部署建议通过环境变量 `VOICE_STUDIO_GATEWAY_KEY` 注入固定 Key；设置环境变量后，界面轮换按钮会被禁用。

    $headers = @{ Authorization = "Bearer <从 API 网关页面复制的 Key>" }
    $body = '{"model":"tts-default","voice":"mimo-default","input":"你好，Voice Studio。","response_format":"wav"}'
    Invoke-WebRequest http://127.0.0.1:8765/v1/audio/speech -Headers $headers -Method Post -ContentType "application/json" -Body $body -OutFile demo.wav

模型 ID 使用 provider/model-id，并提供 tts-default、tts-fast、tts-hq 别名。当前 tts-default 和 tts-hq 指向 mimo/mimo-v2.5-tts。

API 网关页面的“接口测试台”可以先点击“测试模型接口”确认 Key 和模型目录，再选择模型、兼容音色和 mp3/wav 格式测试 `/v1/audio/speech`。成功后页面会显示 HTTP 状态、延迟、Content-Type、任务 ID，并提供试听和下载。测试台生成的示例会随当前请求参数更新；如果模型没有兼容音色，需先在音色库导入或克隆后才能发起测试。

网关错误统一返回 OpenAI 风格的 `error.message`、`error.type` 和 `error.code`，认证失败为 HTTP 401，模型不存在为 HTTP 404，参数校验失败为 HTTP 400。`response_format` 会自动去除首尾空格并按小写处理。选择 `pcm` 时，响应会额外提供 `X-Voice-Studio-PCM-Encoding: s16le`、采样率、声道数和位深响应头；PCM 是裸音频数据，不包含 WAV 文件头，调用方需要根据这些头信息播放或封装。

### SSE 流式语音

网关提供 `POST /v1/audio/speech/stream`。请求体与 `/v1/audio/speech` 相同，额外可传 `chunk_size`（1024–65536，默认 8192）。响应为 `text/event-stream`，每个 `audio` 事件的 `data` 包含一段 Base64 音频，最后以 `done` 事件返回任务 ID、字节数、分片数、`first_chunk_latency_ms` 首片延迟和总耗时；失败时返回 `error` 事件，结构仍为 OpenAI 风格的 `error` 对象。客户端断开连接时，网关会终止上游流并删除未完成的临时音频。

```powershell
$headers = @{ Authorization = "Bearer <从 API 网关页面复制的 Key>" }
$body = '{"model":"tts-default","voice":"mimo-default","input":"你好，这是流式测试。","response_format":"wav","chunk_size":4096}'
curl.exe -N http://127.0.0.1:8765/v1/audio/speech/stream -H "Authorization: Bearer <Key>" -H "Content-Type: application/json" -d $body
```

这是网关统一的 SSE 分片协议，客户端可以边接收边转发或缓存音频。火山引擎 Seed TTS 2.0/声音复刻 2.0、千问 CosyVoice V3 Flash/Plus，以及 MiniMax Speech 2.6/2.8 的 MP3 请求会直接转发厂商原生分片；MiMo V2.5 TTS、VoiceClone 和 VoiceDesign 的 `response_format=pcm` 请求也会直接转发官方 PCM16 原生分片，`done` 事件中的 `native_streaming` 为 `true`。MiMo 原生流是 24 kHz、16-bit、单声道、s16le 裸 PCM，不能直接当作 WAV 播放；MP3/WAV 等格式仍会先完成厂商合成，再由网关分片发送。若需要 OpenAI Python/Node SDK 的标准音频文件写入，请继续使用 `/v1/audio/speech`；SDK 冒烟验证方法见下方示例和项目运行说明。

### 网关运行统计

API 网关页面的“运行统计”直接读取 `GET /api/gateway/stats?window=7d`，支持 `24h`、`7d`、`30d` 和 `all`，还可以用 `provider=dashscope` 等参数筛选厂商。统计记录独立于任务历史，从本版本启用后开始写入：同步请求记录总耗时，流式请求另外记录首片延迟、分片数、音频字节数、原生/兼容分片、成功、失败和客户端取消。P50/P95 只基于实际存在的延迟样本；旧版本任务不会被伪造回填。

### 任务历史、批量导出与存储

生成的任务音频默认保存在项目目录 `data/audio`，SQLite 只保存任务信息和相对路径。任务历史接口为 `GET /api/jobs`，可用 `date=YYYY-MM-DD` 按本机日期筛选，最多返回 500 条。每条新任务会保存 `input_text`，并提供 `text_url` 与 `audio_url`；分别访问这两个地址即可下载 UTF-8 TXT 原文和原始生成音频。例如：

```powershell
$job = (Invoke-RestMethod http://127.0.0.1:8765/api/jobs?limit=1)[0]
Invoke-WebRequest ("http://127.0.0.1:8765" + $job.text_url) -OutFile .\task.txt
Invoke-WebRequest ("http://127.0.0.1:8765" + $job.audio_url) -OutFile .\task.mp3
```

旧版本任务仍可下载数据库中存在的音频，但由于历史结构只保存了字符数，没有原始文字，因此文字下载会显示不可用。

历史页支持勾选任务后批量导出 ZIP，接口为 `POST /api/jobs/export`，请求体可传 `job_ids`，或者传 `date` 导出某一天的全部任务。ZIP 内包含 `manifest.json`、`text/` 和 `audio/`，单次导出音频上限为 512 MB。批量删除接口为 `POST /api/jobs/delete`，单条删除接口为 `DELETE /api/jobs/{job_id}`，两者都会同时删除任务记录与对应音频。存储统计可通过 `GET /api/jobs/storage` 查看。

当前采用“手动可控清理”策略：生成结果默认保留，用户可以先批量导出再删除，避免自动清理误删重要录音。后续如果任务量持续增长，可以再增加按天数自动清理、总容量上限或导出后清理策略，并将其做成设置项而不是默认开启。

已配置厂商账号后，可以运行真实流式冒烟脚本。脚本会依次调用 MiMo V2.5 TTS、火山引擎 Seed TTS 2.0、千问 CosyVoice V3 Flash 和 MiniMax Speech 2.8 Turbo，自动选择兼容音色，记录首片延迟、总耗时、分片数与字节数，并使用 `ffprobe` 验证输出音频。MiMo 原生 PCM 会自动封装为 WAV 后再验证。脚本会读取本地网关 Key，但不会打印 Key。

```powershell
cd E:\Projects\voice-studio
.\backend\.venv\Scripts\python.exe .\backend\tests\live_stream_smoke.py
```

只验证某一家时添加 `--provider mimo`、`--provider volcengine`、`--provider dashscope` 或 `--provider minimax`。音频保存在 `output\live-stream-smoke`，MiMo 输出文件为 WAV，其余厂商为 MP3。

需要验证取消传播时，可加入 `--cancel-after-chunks 1`。脚本会在收到首个分片后断开连接，并检查对应任务没有落库、`data\audio` 中没有遗留半成品。

MiMo 中文音色别名为 mimo-default、bingtang、moli、suda、baihua；英文音色为 mia、chloe、milo、dean。OpenAI 常用音色 alloy、coral、nova、shimmer 在 MiMo 模型下也会映射到兼容音色。

## 配置厂商 API Key

1. 启动 Voice Studio，打开左侧“设置”。
2. 选择通义千问、火山引擎、MiniMax 或小米 MiMo。
3. 填写配置名称和 API Key。Endpoint 已按厂商预填官方默认地址，通常无需修改。
4. 点击“保存账号”。API Key 会直接写入当前 Windows 用户的 Credential Manager。
5. 四家厂商账号均可点击“验证鉴权”；MiniMax 使用文件列表接口校验 Key，不产生语音合成费用。

设置页面和 SQLite 不保存或回显完整 API Key，只记录脱敏后缀。更新账号时密钥框留空即可继续使用原凭据。

千问语音接口需要标准 sk- API Key；sk-sp- Token Plan Key 不支持 TTS。

## 当前真实调用

Qwen3 TTS Flash、Instruct Flash 与非流式 Voice Clone 通过 DashScope HTTP API 合成；CosyVoice V3 Flash/Plus 通过官方 WebSocket SDK 合成。声音复刻会在创建时上传已授权的 WAV、MP3 或 M4A 样本并取得远端 Voice ID，之后合成只发送 Voice ID。创建音色时的目标模型与合成模型必须完全一致。

千问默认 Endpoint 为 `https://dashscope.aliyuncs.com`，不需要填写区域或 Cluster。Qwen3 TTS Instruct Flash 在合成工作台会额外显示“表达指令”输入框。千问参考音频建议 10–20 秒，Qwen3 TTS VC 要求 WAV 16-bit、MP3 或 M4A，不超过 10 MB。

MiMo V2.5 TTS、VoiceClone 和 VoiceDesign 通过官方 `/v1/chat/completions` 接口合成，API Key 在每次请求时从 Windows Credential Manager 读取。Endpoint 使用 `https://api.xiaomimimo.com/v1`，不需要填写区域或 Cluster。官方原生流式请求使用 `stream=true` 和 `audio.format=pcm16`，响应中的 `choices[0].delta.audio.data` 是 Base64 PCM16 分片；网关将其统一包装为 SSE 的 `audio` 事件。

火山引擎使用新版豆包语音 API Key，通过 `/api/v3/tts/unidirectional` 接入 Seed TTS 2.0 和 Seed 声音复刻 2.0。Endpoint 使用 `https://openspeech.bytedance.com`，App ID、区域和 Cluster 均留空。声音复刻通过 `/api/v3/tts/voice_clone` 创建远端音色，后续合成只发送音色 ID；首次正式调用复刻音色合成可能触发厂商音色槽位计费。

MiniMax 中国大陆站默认 Endpoint 为 `https://api.minimaxi.com/v1`，其中 `/v1` 必须保留；同步合成使用 `/t2a_v2`，原生流式使用 `wss://api.minimaxi.com/ws/v1/t2a_v2`，声音复刻使用 `/files/upload` 和 `/voice_clone`。新版 API Reference 使用 Bearer API Key，不需要 Group ID、区域或 Cluster。国际站使用不同域名，需要接入国际站时再手动修改 Endpoint。MiniMax 复刻音频支持 WAV、MP3、M4A，时长 10 秒至 5 分钟且不超过 20 MB；创建时不自动生成收费试听音频。复刻音色若 7 天内未正式调用，厂商可能自动删除。

音色库支持按厂商筛选。点击“导入 Voice ID”后，可以在“云端同步”中直接读取通义千问或 MiniMax 当前账号下的克隆音色，勾选后批量导入；也可以切换到“手工输入 ID”。读取和导入不会创建、删除厂商音色，也不会生成收费音频。

千问云端音色会按创建时的 `target_model` 自动匹配，绑定到尚未接入模型的音色会显示为不兼容。MiniMax 只读取 `voice_cloning` 分类；快速复刻音色至少正式合成过一次后才会出现在厂商查询接口中。同一个 MiniMax Voice ID 可在当前四个 Speech 模型之间共用。

火山引擎支持两种导入方式：选择 `Seed 声音复刻 2.0` 后手工填写控制台中的 `speaker_id`（通常为 `S_...`，后付费自定义音色可能为 `custom_...`），或在“云端同步”模式中读取项目下所有 `Success` / `Active` 音色并批量登记。云端同步需要在“设置 → 火山引擎”额外填写 IAM/OpenAPI Access Key ID、Secret Access Key 和 `ProjectName`；这套 AK/SK 只用于 `BatchListMegaTTSTrainStatus` 管理接口，不能复用新版豆包语音 API Key，也不能使用旧版控制台的 APP ID、Access Token、Secret Key。项目名称必须与火山控制台的声音复刻项目一致。同步不会创建、删除音色或生成收费音频。删除只会从 Voice Studio 本地音色库移除，不会删除厂商控制台中的远端音色；本地保存的参考音频（如有）也会随本地音色一并删除。

MiMo VoiceClone 会把本地保存的已授权参考音频作为请求内音色发送，不会把音频 Base64 写入 SQLite。MiMo VoiceDesign 使用统一的 Voice Design 页面创建和复用请求级音色描述模板。

## 安全与公开发布

- 厂商 API Key、火山 OpenAPI AK/SK 保存在当前 Windows 用户的 Credential Manager，不写入 SQLite、前端构建产物或项目配置文件。
- 本地网关 Key 默认写入 `data/gateway.json`。`data/`、`output/`、日志、虚拟环境、依赖和构建目录均由 `.gitignore` 排除；初始化 Git 仓库后仍应在首次提交前检查待提交文件。
- 服务默认只监听 `127.0.0.1:8765`，不要直接改为 `0.0.0.0` 或映射到公网。网关 Key 可以调用已配置的付费语音接口，应按敏感凭据管理。
- 厂商 Endpoint 默认只接受内置的官方 HTTPS 域名，防止误把 API Key 发送到第三方地址。确实需要可信代理时，可设置 `VOICE_STUDIO_ALLOW_CUSTOM_ENDPOINTS=1`；自定义远程地址仍必须使用 HTTPS，本机地址可以使用 HTTP。
- 浏览器请求仅接受本机 Origin 和 Host。自定义可信来源或主机时，分别使用逗号分隔的 `VOICE_STUDIO_ALLOWED_ORIGINS`、`VOICE_STUDIO_ALLOWED_HOSTS`，不要填写不受信任的域名。

演示适配器生成的是可播放 WAV 音频，用于验证本地页面、持久化和 OpenAI 请求链路，不代表云厂商真实音质。
