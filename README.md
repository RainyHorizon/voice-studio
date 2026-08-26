# Voice Studio

Voice Studio 是一个本地运行的多厂商 AI 语音工作台。它把通义千问、火山引擎、MiniMax 和小米 MiMo 的语音能力集中在一个网页界面中，并提供 OpenAI 兼容 API，方便其他应用调用。

API Key、音频、任务历史和音色信息默认保存在本机，不会上传到 Voice Studio 服务端。

## 主要功能

| 功能 | 说明 |
| --- | --- |
| 语音合成 | 按厂商、模型和音色生成语音，支持试听与下载 |
| 声音克隆 | 上传已获授权的参考音频，创建可复用音色 |
| 声音设计 | 用文字描述声音特征并生成试听音色 |
| 音色库 | 按厂商筛选，管理预置、导入、克隆和设计音色 |
| 任务历史 | 查看生成记录，下载音频和文字，批量导出 ZIP 或删除记录 |
| 存储策略 | 设置音频保留天数、容量上限和自动清理周期 |
| API 网关 | 提供 OpenAI 兼容的模型、语音合成和 SSE 流式接口 |
| 运行诊断 | 查看 Python、FFmpeg、凭据存储和前端状态 |

声音克隆和声音设计只能用于你已经获得授权的声音或描述，并应遵守相关法律及厂商条款。

## 厂商能力

| 厂商 | 语音合成 | 声音克隆 | 声音设计 | 已有云端音色导入 |
| --- | :---: | :---: | :---: | :---: |
| 通义千问 | 支持 | 支持 | 支持 | 支持 |
| 火山引擎 | 支持 | 支持 | 不支持 | 支持 |
| MiniMax | 支持 | 支持 | 支持 | 支持 |
| 小米 MiMo | 支持 | 支持 | 支持 | 不提供 |

每个厂商可用的模型、音色、地区和额度不同，最终以应用中的模型列表及厂商控制台为准。

## 运行方式

| 方式 | 推荐对象 | 需要安装 |
| --- | --- | --- |
| Windows 便携版 | 普通 Windows 用户 | 不需要 Python、Node.js 或 FFmpeg |
| Windows 轻量版 | 已安装运行环境的 Windows 用户 | Python 3.11+、FFmpeg |
| 源码启动 | Windows、macOS、Linux 开发者 | Python 3.11+、FFmpeg；首次构建前端需要 Node.js 20+ |
| Docker Compose | 服务器或容器用户 | Docker Desktop 或 Docker Engine + Compose |

### Windows 便携版

1. 在 [Releases](https://github.com/RainyHorizon/voice-studio/releases) 下载 `Voice-Studio-*-Windows-Portable.zip`。
2. 将压缩包完整解压到有写入权限的普通文件夹，不要直接在压缩包预览窗口中运行。
3. 双击 `启动 Voice Studio.bat`。
4. 浏览器打开启动器显示的地址，默认是 `http://127.0.0.1:8765`。

便携版包含运行所需的 Python、后端依赖、前端文件、FFmpeg 和 FFprobe。数据库、音频和网关配置保存在程序目录的 `data` 文件夹中。升级时请保留这个文件夹。

从首个包含自动更新器的版本开始，可先关闭 Voice Studio，再双击 `更新 Voice Studio.bat`。更新器会自动识别 Portable、Windows 轻量版或 Git 源码目录，并选择对应的安全更新方式。更早的便携版需要先手动升级一次。

### Windows 轻量版

在 Releases 下载 `Voice-Studio-*-Windows.zip` 并完整解压，安装 Python 3.11+ 和 FFmpeg 后，双击 `启动 Voice Studio.bat`。轻量版已包含预构建前端，通常不需要安装 Node.js。

### Windows 源码启动

先安装 Python 3.11+ 和 FFmpeg，并将它们加入系统 `Path`。如果仓库没有预构建的前端文件，还需要 Node.js 20+。

```powershell
git clone https://github.com/RainyHorizon/voice-studio.git
Set-Location voice-studio
.\start.ps1 -OpenBrowser
```

不希望自动打开浏览器时运行：

```powershell
.\start.ps1
```

指定端口示例：

```powershell
.\start.ps1 -Port 8766 -OpenBrowser
```

### macOS / Linux 源码启动

安装 Python 3.11+、FFmpeg/FFprobe，并确保当前用户可以使用系统密钥环（macOS Keychain，或 Linux Secret Service、GNOME Keyring、KWallet）。

```bash
git clone https://github.com/RainyHorizon/voice-studio.git
cd voice-studio
chmod +x start.sh
./start.sh --open-browser
```

`start.sh` 会自动创建 `backend/.venv`、安装后端依赖，并在需要时构建前端。

## 更新

| 当前安装方式 | 更新入口 | 更新来源 |
| --- | --- | --- |
| Windows Portable | 双击 `更新 Voice Studio.bat` | 最新正式版 Portable ZIP |
| Windows 轻量版 | 双击 `更新 Voice Studio.bat` | 最新正式版 Windows ZIP |
| Windows Git 源码 | 双击 `更新 Voice Studio.bat` | 当前分支的上游 Git 分支 |
| Windows Source ZIP | 双击 `更新 Voice Studio.bat` | 最新正式版 Windows ZIP |
| macOS / Linux Release 包 | `bash update.sh` | 对应系统的最新正式版 TAR 包 |
| macOS / Linux Git 源码 | `bash update.sh` | 当前分支的上游 Git 分支 |
| macOS / Linux Source ZIP | `bash update.sh` | 对应系统的最新正式版 TAR 包 |

Release 包更新前会校验 GitHub 提供的 SHA256，只替换清单内的程序文件，并保留 `data`、系统凭据、虚拟环境和其他用户文件。没有 `.git` 的 GitHub Source ZIP 会在首次更新后转为对应系统的 Release 包维护。Git 更新只允许官方仓库、已配置上游且工作区完全干净的分支，并使用 `git pull --ff-only`；存在本地改动或分叉历史时会停止，不会覆盖代码。

只检查更新：

```powershell
.\update.ps1 -CheckOnly
```

```bash
bash update.sh --check
```

## Docker Compose

Docker 使用环境变量读取厂商密钥，不访问宿主机的系统密钥环。

```bash
git clone https://github.com/RainyHorizon/voice-studio.git
cd voice-studio
cp .env.example .env
```

编辑 `.env`，至少设置一个随机的 `VOICE_STUDIO_GATEWAY_KEY`，然后启动：

```bash
docker compose up -d
docker compose ps
docker compose logs -f voice-studio
```

默认地址为 `http://127.0.0.1:8765`。停止服务但保留 `data` 数据：

```bash
docker compose down
```

Docker 镜像不使用桌面更新脚本。更新 `.env` 中的 `VOICE_STUDIO_VERSION` 后执行：

```bash
docker compose pull
docker compose up -d --no-build
```

如果使用本地源码构建镜像，则先更新 Git 源码，再执行 `docker compose up -d --build`。`./data` 挂载目录和 `.env` 不会被镜像更新覆盖。

首次使用本地源码构建镜像：

```bash
docker compose up -d --build
```

## 配置厂商 API Key

启动后进入 **设置**，选择厂商并填写 API Key。Endpoint 已预填官方地址，通常不需要修改。只有厂商账号或网络环境明确要求时才调整。

桌面版默认使用当前用户的系统密钥环：

| 系统 | 保存位置 |
| --- | --- |
| Windows | Windows Credential Manager |
| macOS | Keychain |
| Linux | Secret Service（GNOME Keyring/KWallet） |
| Docker | `.env` 或部署平台 Secret |

Docker 可用变量：

| 变量 | 用途 |
| --- | --- |
| `VOICE_STUDIO_GATEWAY_KEY` | OpenAI 兼容 API 的 Bearer Key，必填 |
| `VOICE_STUDIO_DASHSCOPE_API_KEY` | 通义千问 API Key |
| `VOICE_STUDIO_VOLCENGINE_API_KEY` | 火山引擎语音 API Key |
| `VOICE_STUDIO_VOLCENGINE_OPENAPI_ACCESS_KEY` | 火山引擎云端音色同步 Access Key |
| `VOICE_STUDIO_VOLCENGINE_OPENAPI_SECRET_KEY` | 火山引擎云端音色同步 Secret Key |
| `VOICE_STUDIO_VOLCENGINE_PROJECT_NAME` | 火山引擎项目名称 |
| `VOICE_STUDIO_MINIMAX_API_KEY` | MiniMax API Key |
| `VOICE_STUDIO_MIMO_API_KEY` | 小米 MiMo API Key |

火山引擎的语音 API Key 与云端音色同步使用的 Access Key/Secret Key 是两组不同凭据。不使用云端音色同步时，后两项可以留空。`.env` 只保存在本机，不要提交到 GitHub。

## OpenAI 兼容 API

在 **API 网关** 页面查看或轮换 Gateway Key。默认 Base URL：

```text
http://127.0.0.1:8765/v1
```

所有请求都需要：

```http
Authorization: Bearer <Gateway Key>
```

| 接口 | 方法 | 用途 |
| --- | --- | --- |
| `/v1/models` | `GET` | 查询可用模型及支持的操作 |
| `/v1/audio/speech` | `POST` | 生成完整音频 |
| `/v1/audio/speech/stream` | `POST` | 通过 SSE 接收音频分片 |

`model` 可以填写 API 网关页面显示的完整模型 ID，也可以使用 `tts-default`、`tts-fast` 或 `tts-hq`。`voice` 必须与所选模型兼容。

### Python SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="<Gateway Key>",
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
  apiKey: "<Gateway Key>",
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

普通 OpenAI SDK 使用 `/v1/audio/speech`。需要边接收边处理音频时，再使用 `/v1/audio/speech/stream`。

## 数据与存储

| 数据 | 默认位置 |
| --- | --- |
| 生成音频、参考音频 | `data/audio` |
| 任务、音色和账号元数据 | `data/voice_studio.db` |
| 本地 Gateway Key | `data/gateway.json`（Docker 优先使用环境变量） |

在 **设置 → 存储与清理** 中可以配置自动清理、音频保留天数、容量上限和检查周期。需要长期保存时，先在 **任务历史** 导出文字和音频，再启用自动清理。

PCM 是不带文件头的原始音频数据，浏览器通常无法直接播放。日常使用建议选择 MP3 或 WAV；PCM 适合流式处理或专业音频软件。

## 安全提示

- 厂商密钥默认保存在系统密钥环，不写入 SQLite、前端文件或 Git。
- 页面只显示脱敏后的密钥，浏览器不会直接请求厂商 API。
- 服务默认只监听 `127.0.0.1`。不要在没有 HTTPS、访问控制和限流的情况下暴露到公网。
- Gateway Key 具有调用已配置付费语音接口的权限，请像保护厂商 API Key 一样保护它。
- Docker 使用 `.env` 或平台 Secret 注入密钥；不要提交 `.env`、数据库、音频和日志。
- 不要把自定义 Endpoint 指向不可信域名，以免 API Key 被发送到错误的目标。

## 技术架构

| 层级 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite |
| 后端 | FastAPI、Python |
| 本地数据 | SQLite、文件系统 |
| 厂商连接 | HTTP、WebSocket |
| 兼容接口 | OpenAI 风格 REST API、SSE |
| 部署 | Windows 便携版、跨平台源码启动、Docker Compose |

浏览器或 OpenAI 客户端 → FastAPI 本地服务 → 厂商语音 API；前端不直接携带厂商 API Key。

## 开发与测试

```powershell
# 前端
Set-Location frontend
npm ci
npm run build

# 后端测试
Set-Location ..\backend
python -m pip install -r requirements.txt
python -m pip install pytest==8.3.5
python -m pytest -q tests
```

测试不会调用真实厂商 API。真实语音测试可能产生费用或消耗额度，请先确认账号权限和计费规则。

## 当前限制

- 项目主要面向单用户本地运行，不是多租户云服务。
- 厂商可能调整模型名称、接口、计费和权限要求。
- 克隆、设计和云端音色同步能力取决于厂商账号、地区、额度和模型权限。
- OpenAI 兼容网关覆盖常用语音接口，不保证覆盖 OpenAI 的全部字段。
- Windows 便携版目前未进行商业代码签名，SmartScreen 可能显示“未知发布者”。可使用 Release 中的 SHA256 文件校验下载完整性。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。第三方依赖及其许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
