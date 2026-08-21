# Voice Studio

Voice Studio 是一个在 Windows 本地运行的多厂商 AI 语音工作台。它将通义千问、火山引擎、MiniMax 和小米 MiMo 的语音能力集中在一个界面中，并提供 OpenAI 兼容 API，方便其他应用调用。

## 功能概览

| 功能 | 说明 |
| --- | --- |
| 语音合成 | 选择厂商、模型和音色，生成、试听并下载语音 |
| 声音克隆 | 上传已获授权的参考音频，创建可复用音色 |
| 声音设计 | 根据文字描述设计新音色并生成试听音频 |
| 音色库 | 按厂商筛选、导入、同步和管理音色 |
| 任务历史 | 按日期查看任务，下载文字与音频，支持批量导出 ZIP 和批量删除 |
| 存储策略 | 设置自动保留天数、容量上限和定期清理规则 |
| API 网关 | 提供 OpenAI 兼容的模型查询、语音合成和流式语音接口 |
| 运行统计 | 查看网关请求量、成功率、延迟和错误情况 |

## 支持的厂商

| 厂商 | 语音合成 | 声音克隆 | 声音设计 | 云端克隆音色导入 |
| --- | :---: | :---: | :---: | :---: |
| 通义千问 | 支持 | 支持 | 支持 | 支持 |
| 火山引擎 | 支持 | 支持 | - | 支持 |
| MiniMax | 支持 | 支持 | 支持 | 支持 |
| 小米 MiMo | 支持 | 支持 | 支持 | - |

<details>
<summary>查看当前内置模型</summary>

| 厂商 | 模型 |
| --- | --- |
| 通义千问 | Qwen3 TTS Flash、Qwen3 TTS Instruct Flash、Qwen3 TTS VC、CosyVoice V3 Flash、CosyVoice V3 Plus、Qwen3 TTS VoiceDesign |
| 火山引擎 | Seed TTS 2.0、Seed 声音复刻 2.0 |
| MiniMax | Speech 2.8 HD/Turbo、Speech 2.6 HD/Turbo |
| 小米 MiMo | MiMo V2.5 TTS、VoiceClone、VoiceDesign |

</details>

模型是否可用取决于厂商当前接口、账号权限、所在地区和音色额度。调用真实厂商接口可能产生费用，请以对应厂商控制台为准。

## 快速开始

### 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 或 Windows 11 |
| Python | Python 3.11 或更高版本 |
| Node.js | 仅从源码首次构建前端时需要；Windows Release 不需要 |
| FFmpeg | `ffmpeg` 和 `ffprobe` 可通过系统 `Path` 调用 |
| 网络 | 能够访问所使用厂商的官方 API |

### 下载项目

普通用户优先下载 GitHub **Releases** 页面中的 `Voice-Studio-*-Windows.zip`。该压缩包已经包含前端文件，运行时不需要安装 Node.js。

使用 GitHub 的 **Code → Download ZIP** 或 Git 克隆得到的是源码版，首次启动需要 Node.js：

```powershell
git clone https://github.com/RainyHorizon/voice-studio.git
cd voice-studio
```

### 一键启动

双击项目根目录中的：

```text
启动 Voice Studio.bat
```

首次启动会创建 Python 虚拟环境并安装后端依赖；源码版还会构建前端，Windows Release 会跳过这一步。所需时间取决于网络速度，启动完成后会自动打开：

```text
http://127.0.0.1:8765
```

启动时会检查 Python、FFmpeg、FFprobe、数据目录和 Windows Credential Manager。如果默认端口被其他程序占用，程序会自动尝试 `8766` 至 `8790`，并在窗口中显示实际地址。

也可以在 PowerShell 中启动：

```powershell
Set-Location <Voice Studio 所在目录>
.\start.ps1
```

需要固定使用其他端口时：

```powershell
.\start.ps1 -Port 8766 -OpenBrowser
```

服务器窗口需要在使用期间保持运行。关闭服务器窗口即可停止 Voice Studio。

## 首次使用

1. 打开左侧 **设置**，选择需要使用的语音厂商。
2. 填写该厂商的 API Key，Endpoint 通常保持默认值，然后保存账号。
3. 返回 **合成工作台**，选择厂商、模型和音色。
4. 输入文字并生成语音，结果会出现在页面下方和 **任务历史** 中。

尚未准备 API Key 时，可以在合成工作台选择 **本地演示 → 本地演示音频**，或进入 **设置 → 运行环境** 点击 **运行演示**。它只在本机生成测试 WAV，不调用厂商接口，也不会消耗额度。

不同厂商使用不同凭据。火山引擎的豆包语音 API Key 用于语音生成；只有同步云端克隆音色时，才需要额外填写 IAM/OpenAPI Access Key ID、Secret Access Key 和项目名称。

## 主要页面

| 页面 | 用途 |
| --- | --- |
| 合成工作台 | 完成日常语音生成，调整模型、音色、语速和输出格式 |
| 音色库 | 管理预置、导入、克隆和设计音色，并按厂商筛选 |
| 声音克隆 | 上传参考音频，为支持的模型创建声音克隆 |
| 声音设计 | 使用文字描述创建通义千问、MiniMax 或 MiMo 设计音色 |
| API 网关 | 查看本地 Gateway Key、测试接口并查看运行统计 |
| 任务历史 | 试听、下载、批量导出或删除已生成任务 |
| 设置 | 配置厂商账号，以及管理音频存储和自动清理策略 |

在 **设置 → 运行环境** 中可以重新检查 Python、FFmpeg、FFprobe、前端文件、Node.js、Credential Manager 和数据目录状态。Node.js 在 Windows Release 中属于可选项。

## OpenAI 兼容 API

在 **API 网关** 页面可以查看本地 Gateway Key、查询可用模型并直接测试接口。

| 项目 | 地址 |
| --- | --- |
| Base URL | `http://127.0.0.1:8765/v1` |
| 模型列表 | `GET /v1/models` |
| 语音合成 | `POST /v1/audio/speech` |
| SSE 流式语音 | `POST /v1/audio/speech/stream` |

请求中的 `model` 可以使用页面显示的完整模型 ID，也可以使用 `tts-default`、`tts-fast` 或 `tts-hq`。`voice` 必须与所选模型兼容。

下面的示例使用 MiMo 默认音色。请先配置小米 MiMo，或在 API 网关测试台中换成已经配置的模型和兼容音色。

### Python SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="<API 网关页面中的 Gateway Key>",
    base_url="http://127.0.0.1:8765/v1",
)

with client.audio.speech.with_streaming_response.create(
    model="tts-default",
    voice="mimo-default",
    input="你好，这是 Voice Studio 生成的语音。",
    response_format="mp3",
) as response:
    response.stream_to_file("speech.mp3")
```

### Node.js SDK

```javascript
import { writeFile } from "node:fs/promises";
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "<API 网关页面中的 Gateway Key>",
  baseURL: "http://127.0.0.1:8765/v1",
});

const response = await client.audio.speech.create({
  model: "tts-default",
  voice: "mimo-default",
  input: "你好，这是 Voice Studio 生成的语音。",
  response_format: "mp3",
});

await writeFile("speech.mp3", Buffer.from(await response.arrayBuffer()));
```

普通 OpenAI SDK 音频文件写入请使用 `/v1/audio/speech`。`/v1/audio/speech/stream` 使用 Voice Studio 的 SSE 音频分片协议，适合需要边接收边处理音频的客户端。

## 音频与存储

| 数据 | 保存位置 |
| --- | --- |
| 生成音频和参考音频 | `data/audio` |
| 任务、音色和账号元数据 | `data/voice_studio.db` |
| 本地 Gateway Key | `data/gateway.json`，或由 `VOICE_STUDIO_GATEWAY_KEY` 环境变量提供 |
| 厂商 API Key、火山引擎 AK/SK | Windows Credential Manager |
| 测试输出 | `output` |

在 **设置 → 存储与清理** 中可以配置：

- 自动清理开关；
- 音频保留天数；
- 最大存储容量；
- 每日或每周检查；
- 只清理音频，或同时删除任务记录；
- 清理前预览和立即清理。

默认策略不会自动删除文件。启用自动清理前，建议先在任务历史中导出需要长期保存的内容。

## 安全说明

- 厂商 API Key 与火山引擎 AK/SK 通过 Windows Credential Manager 保存，不写入项目配置文件、SQLite 数据库或前端构建产物。
- 账号接口只显示脱敏后的密钥末四位，不会向前端返回完整厂商密钥。
- `data`、`output`、日志、虚拟环境、依赖和构建目录均已通过 `.gitignore` 排除。
- 服务默认只监听 `127.0.0.1:8765`，请勿直接改为 `0.0.0.0` 或暴露到公网。
- Gateway Key 可以调用已经配置的付费语音接口，应按敏感凭据管理，不要提交到 GitHub 或发送给他人。
- 自定义厂商 Endpoint 可能导致密钥被发送到第三方地址。没有明确需要时，请使用程序预填的官方 Endpoint。
- 声音克隆前必须获得声音所有者授权，并遵守当地法律和厂商使用条款。

Credential Manager 可以降低明文配置和误提交造成的泄露风险，但不能抵御已经控制当前 Windows 账户的恶意程序。请同时保护 Windows 账户，并在怀疑泄露时立即前往厂商控制台轮换密钥。

## 技术架构

| 层级 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite |
| 后端 | FastAPI、Python |
| 本地数据库 | SQLite |
| 凭据存储 | Windows Credential Manager |
| 厂商连接 | HTTP、WebSocket |
| 兼容接口 | OpenAI 风格 REST API、SSE |

```text
浏览器界面 / OpenAI 客户端
              │
              ▼
       FastAPI 本地服务
          │         │
          ▼         ▼
 SQLite 与音频文件   语音厂商 API
```

所有厂商适配、凭据读取和文件写入都在本地后端完成。浏览器前端不会直接携带厂商 API Key 请求第三方服务。

## 常见问题

### 双击启动文件后没有打开页面

检查启动窗口中的中文诊断结果，其中会明确显示 Python、FFmpeg、依赖安装、凭据存储或端口占用错误。也可以通过 PowerShell 运行 `.\start.ps1` 查看完整信息。

### 提示找不到 Node.js，但我只想使用程序

GitHub 源码不包含前端构建产物，因此源码版首次启动需要 Node.js。普通用户应下载 Releases 页面中的 Windows ZIP，该版本不需要 Node.js。

### 8765 端口被占用怎么办

双击启动时会自动寻找 `8766` 至 `8790`。需要固定端口时运行 `.\start.ps1 -Port 8766 -OpenBrowser`；API 网关页面会显示与实际端口一致的 Base URL。

### 已填写 API Key，为什么仍然生成失败

先在 **设置** 中执行鉴权验证，然后检查所选模型是否已对当前账号开放、音色是否与模型兼容，以及厂商账号是否还有可用额度。

### 为什么部分音色无法用于当前模型

不同模型的音色 ID 通常不能混用。切换模型后，Voice Studio 会自动筛选兼容音色；云端导入的音色也会保留其厂商和目标模型信息。

### 生成的音频会一直占用空间吗

默认会保存在 `data/audio`。可以在 **任务历史** 中导出后删除，也可以在 **设置 → 存储与清理** 中启用自动清理。

### PCM 为什么不能直接在浏览器播放

PCM 是不带文件头的原始音频数据，播放器无法自动识别采样率、位深和声道数。日常下载建议使用 MP3 或 WAV；PCM 更适合流式处理和专业音频程序。

## 开发与测试

构建前端：

```powershell
Set-Location frontend
npm install
npm run build
```

运行后端测试：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests
```

普通自动化测试不会调用真实厂商接口。真实语音测试可能消耗额度或产生费用，请在明确了解测试内容后再运行相关脚本。

构建不包含用户数据和密钥的 Windows Release：

```powershell
.\build-windows-release.ps1
```

压缩包会生成到 `output\releases`，包含后端代码、预构建前端、启动脚本、README 和许可证，不包含 `data` 中的本地数据库、音频、Gateway Key、虚拟环境或依赖目录。

## 当前限制

- 当前版本主要面向 Windows 单用户本地运行，不是云端多用户服务。
- 厂商可能调整模型名称、接口、计费方式和权限要求。
- 声音克隆与声音设计能力取决于账号权限和厂商音色槽位。
- API 网关以本地兼容和应用接入为目标，不保证覆盖 OpenAI API 的全部字段。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
