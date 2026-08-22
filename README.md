# Voice Studio

Voice Studio 是一个在 Windows、macOS 和 Linux 本地运行的多厂商 AI 语音工作台。它将通义千问、火山引擎、MiniMax 和小米 MiMo 的语音能力集中在一个界面中，并提供 OpenAI 兼容 API，方便其他应用调用。

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
| 操作系统 | Windows 10/11、macOS 12+ 或主流 Linux 发行版 |
| Python | 便携版不需要；轻量版和源码版需要 Python 3.11 或更高版本 |
| Node.js | 仅从源码首次构建前端时需要 |
| FFmpeg | 便携版已包含；轻量版和源码版需要加入系统 `Path` |
| 系统密钥环 | Windows Credential Manager、macOS 钥匙串，或 Linux Secret Service（GNOME Keyring/KWallet） |
| 网络 | 能够访问所使用厂商的官方 API |

### 下载项目

普通用户优先下载 GitHub **Releases** 页面中的 `Voice-Studio-*-Windows-Portable.zip`。便携版已经包含 Python 运行时、后端依赖、前端文件、FFmpeg 和 FFprobe，完整解压后即可使用。

体积较小的 `Voice-Studio-*-Windows.zip` 是轻量版，不需要 Node.js，但仍要求电脑已经安装 Python 3.11+ 与 FFmpeg。

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

轻量版首次启动会创建 Python 虚拟环境并安装后端依赖；源码版还会构建前端。便携版不安装运行依赖，启动完成后会自动打开：

```text
http://127.0.0.1:8765
```

启动时会检查 Python、FFmpeg、FFprobe、数据目录和当前系统的密钥环。如果默认端口被其他程序占用，Windows 启动脚本会自动尝试 `8766` 至 `8790`；macOS/Linux 请使用 `--port` 指定可用端口。

也可以在 PowerShell 中启动：

```powershell
Set-Location <Voice Studio 所在目录>
.\start.ps1
```

需要固定使用其他端口时：

```powershell
.\start.ps1 -Port 8766 -OpenBrowser
```

### macOS / Linux 启动

macOS 和 Linux 使用源码启动。先安装 Python 3.11+、FFmpeg/FFprobe，以及首次构建前端所需的 Node.js 20+，然后在项目目录执行：

```bash
chmod +x start.sh
./start.sh --open-browser
```

`start.sh` 会自动创建 `backend/.venv`、安装后端依赖，并在 `frontend/dist` 不存在或源码更新时构建前端。日常启动只需要 Python、FFmpeg/FFprobe 和系统密钥环；如果已经有预构建前端，则不需要 Node.js。

常用选项：

```bash
./start.sh                 # 启动服务，不自动打开浏览器
./start.sh --open-browser # 启动后打开默认浏览器
./start.sh --port 8766    # 使用其他端口
```

#### 系统密钥环准备

API Key 不会保存到 `.env` 或 SQLite，而是写入当前用户的系统密钥环：

| 系统 | 使用的安全存储 | 准备方式 |
| --- | --- | --- |
| macOS | 钥匙串（Keychain） | 系统自带；首次写入时允许终端或 Python 访问钥匙串 |
| Linux 桌面 | Secret Service | 安装并启动 GNOME Keyring 或 KWallet，确保当前桌面会话有 D-Bus 密钥环 |
| Linux 服务器/SSH | 取决于会话 | 需要配置可用的 Secret Service 会话；没有图形会话时“打开目录”只返回路径，服务不会伪造明文存储 |

Linux 安装依赖时会自动安装 Python `secretstorage` 包。如果诊断仍显示密钥环不可用，请先登录桌面会话并解锁密钥环，再重新运行 `./start.sh`。不要通过 `KEYRING_BACKEND` 切换到明文后端。

启动终端需要在使用期间保持运行。按 `Ctrl+C` 或关闭终端即可停止 Voice Studio。

### Docker 启动

Docker 版本适合服务器或不希望安装 Python/Node.js 的环境。它使用 Docker volume 或宿主机 `data` 目录保存 SQLite、任务历史和音频，并通过环境变量读取厂商密钥。容器不会读取宿主机的 Windows Credential Manager、macOS 钥匙串或 Linux 密钥环。

```bash
cp .env.example .env
# 编辑 .env，至少设置 VOICE_STUDIO_GATEWAY_KEY
docker compose up -d --build
```

服务默认只绑定到本机 `http://127.0.0.1:8765`。查看状态和日志：

```bash
docker compose ps
docker compose logs -f voice-studio
```

停止服务但保留 `data`：

```bash
docker compose down
```

Docker 环境变量账号会在页面中显示为“Docker 环境变量”，只能通过 `.env` 或部署平台 Secret 修改，不能在网页中覆盖。修改 `.env` 后需要重新创建容器（`docker compose up -d`）才能生效。支持的变量如下：

| 环境变量 | 用途 |
| --- | --- |
| `VOICE_STUDIO_GATEWAY_KEY` | OpenAI 兼容网关的 Bearer Key，必填 |
| `VOICE_STUDIO_DASHSCOPE_API_KEY` | 通义千问 API Key |
| `VOICE_STUDIO_VOLCENGINE_API_KEY` | 火山引擎语音 API Key |
| `VOICE_STUDIO_VOLCENGINE_OPENAPI_ACCESS_KEY` | 火山引擎云端音色同步 AK |
| `VOICE_STUDIO_VOLCENGINE_OPENAPI_SECRET_KEY` | 火山引擎云端音色同步 SK |
| `VOICE_STUDIO_VOLCENGINE_PROJECT_NAME` | 火山引擎项目名称 |
| `VOICE_STUDIO_MINIMAX_API_KEY` | MiniMax API Key |
| `VOICE_STUDIO_MIMO_API_KEY` | 小米 MiMo API Key |

不要把 `.env` 提交到 GitHub，也不要把密钥写入 Dockerfile、Compose 文件、镜像标签或 GitHub Actions 日志。公网部署还需要 HTTPS 反向代理、访问控制和请求限流；当前 Compose 默认仅允许本机访问。

### GitHub Actions 自动构建

仓库内置三类工作流：

| 工作流 | 触发条件 | 作用 |
| --- | --- | --- |
| `CI` | 推送或 PR 到 `main` | 在 Ubuntu、macOS、Windows 上安装依赖、构建前端、运行测试，并验证 Docker 镜像和 Compose 配置 |
| `Build Release Assets` | 推送 `v*.*.*` Tag | 生成 Windows 轻量 ZIP，以及 macOS/Linux 的预构建前端源码包，并创建 GitHub Release |
| `Publish Docker Image` | 推送 `v*.*.*` Tag，或手动运行 | 构建并推送 `linux/amd64`、`linux/arm64` 镜像到 `ghcr.io` |

macOS/Linux Release 当前是“预构建前端源码包”，仍需系统 Python、FFmpeg 和密钥环；它不是签名的 `.app`、`.dmg` 或 AppImage。若未来增加原生安装器，还需要分别处理 macOS 公证、Windows 代码签名和 Linux 发行版兼容性。

发布版本时，先将代码合并到 `main`，再创建版本 Tag，例如：

```bash
git tag v0.6.0
git push origin v0.6.0
```

Actions 会自动运行测试、构建平台包、创建 Release，并推送对应版本的 Docker 镜像。GitHub Actions 不需要厂商 API Key；这些 Key 只在用户部署 Docker 容器时通过 `.env` 或 Secret 注入。

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

在 **设置 → 运行环境** 中可以重新检查 Python、FFmpeg、FFprobe、前端文件、Node.js、系统密钥环和数据目录状态。预构建前端存在时，Node.js 属于可选项。

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
| 厂商 API Key、火山引擎 AK/SK | 当前用户的系统密钥环 |
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

- 厂商 API Key 与火山引擎 AK/SK 通过当前系统的安全密钥环保存，不写入项目配置文件、SQLite 数据库或前端构建产物。
- 账号接口只显示脱敏后的密钥末四位，不会向前端返回完整厂商密钥。
- `data`、`output`、日志、虚拟环境、依赖和构建目录均已通过 `.gitignore` 排除。
- 服务默认只监听 `127.0.0.1:8765`，请勿直接改为 `0.0.0.0` 或暴露到公网。
- Gateway Key 可以调用已经配置的付费语音接口，应按敏感凭据管理，不要提交到 GitHub 或发送给他人。
- 自定义厂商 Endpoint 可能导致密钥被发送到第三方地址。没有明确需要时，请使用程序预填的官方 Endpoint。
- 声音克隆前必须获得声音所有者授权，并遵守当地法律和厂商使用条款。

系统密钥环可以降低明文配置和误提交造成的泄露风险，但不能抵御已经控制当前用户账户的恶意程序。请同时保护操作系统账户，并在怀疑泄露时立即前往厂商控制台轮换密钥。

## 技术架构

| 层级 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite |
| 后端 | FastAPI、Python |
| 本地数据库 | SQLite |
| 凭据存储 | Windows Credential Manager / macOS Keychain / Linux Secret Service / Docker 环境变量 |
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

构建解压即用的 Windows 便携版：

```powershell
.\build-windows-portable.ps1
```

便携版通过 PyInstaller 打包 Python 运行时和后端依赖，并附带本机 FFmpeg 发布目录中的 `ffmpeg.exe`、`ffprobe.exe`、许可证及构建说明。构建机需要 Node.js、Python 3.11+、FFmpeg/FFprobe；最终用户不需要安装这些组件。便携版同样不会包含本地数据库、音频、日志、API Key 或 Gateway Key。

构建脚本会同时生成 `.zip.sha256` 校验文件。当前 EXE 没有商业代码签名，Windows SmartScreen 可能显示“未知发布者”；请只从本项目 GitHub Releases 下载，并在发布页提供 SHA256 文件供用户核对。

## 当前限制

- 当前版本主要面向单用户本地运行，不是云端多用户服务；Windows 便携版仍是最省事的分发方式。
- 厂商可能调整模型名称、接口、计费方式和权限要求。
- 声音克隆与声音设计能力取决于账号权限和厂商音色槽位。
- API 网关以本地兼容和应用接入为目标，不保证覆盖 OpenAI API 的全部字段。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
