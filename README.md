# Voice Studio

Voice Studio 是一个本地运行的多厂商 AI 语音工作台。它把通义千问、火山引擎、MiniMax 和小米 MiMo 的语音合成、声音克隆与声音设计能力集中到一个简洁的网页界面中，并提供 OpenAI 兼容 API，方便其他应用接入。

项目定位是“个人本地工具”，API Key、音频、任务历史和音色元数据默认保存在本机，不上传到 Voice Studio 服务端。

## 功能

| 功能 | 说明 |
| --- | --- |
| 语音合成 | 选择厂商、模型、音色和输出格式，生成、试听与下载语音 |
| 声音克隆 | 上传已获授权的参考音频，创建可复用音色 |
| 声音设计 | 使用文字描述创建新音色并生成试听音频 |
| 音色库 | 按厂商筛选，管理预置、导入、克隆和设计音色 |
| 任务历史 | 按日期查看、下载、批量导出 ZIP 或删除生成任务 |
| 存储策略 | 设置保留天数、容量上限和定期清理规则 |
| API 网关 | 提供 OpenAI 兼容的模型查询、语音合成和 SSE 流式接口 |
| 运行统计 | 查看请求量、成功率、延迟和错误情况 |

### 厂商能力

| 厂商 | 语音合成 | 声音克隆 | 声音设计 | 云端克隆音色同步 |
| --- | :---: | :---: | :---: | :---: |
| 通义千问 | 支持 | 支持 | 支持 | 支持 |
| 火山引擎 | 支持 | 支持 | 不提供 | 支持 |
| MiniMax | 支持 | 支持 | 支持 | 支持 |
| 小米 MiMo | 支持 | 支持 | 支持 | 不提供 |

实际可用模型、音色、地区和额度以厂商控制台及当前账号权限为准。声音克隆和声音设计只应使用已获得授权的声音或描述。

## 选择运行方式

| 方式 | 适合人群 | 依赖 |
| --- | --- | --- |
| Windows 便携版 | 普通 Windows 用户，解压即用 | 无需单独安装 Python、Node.js、FFmpeg |
| Windows/macOS/Linux 轻量版 | 已有开发环境的本地用户 | Python 3.11+、FFmpeg；源码首次构建前端需要 Node.js 20+ |
| Docker Compose | 服务器、容器用户或希望隔离运行环境的用户 | Docker Desktop 或 Docker Engine + Compose |

## 快速开始

### Windows 便携版（推荐）

1. 打开 GitHub 仓库的 [Releases](https://github.com/RainyHorizon/voice-studio/releases) 页面。
2. 下载 <code>Voice-Studio-*-Windows-Portable.zip</code>。
3. 将 ZIP 完整解压到一个有写入权限的目录。
4. 双击 <code>启动 Voice Studio.bat</code>。
5. 浏览器打开 <code>http://127.0.0.1:8765</code>；如果端口被占用，启动器会自动尝试后续端口。

便携版会将数据库、音频和日志写入解压目录下的 <code>data</code>，不会包含发布者的 API Key。

### Windows 轻量版或源码版

安装 Python 3.11+、FFmpeg/FFprobe，并确保它们已加入系统 <code>Path</code>。源码版首次构建前端还需要 Node.js 20+。

~~~powershell
git clone https://github.com/RainyHorizon/voice-studio.git
Set-Location voice-studio
.\start.ps1 -OpenBrowser
~~~

不希望自动打开浏览器时运行：

~~~powershell
.\start.ps1
~~~

### macOS / Linux

安装 Python 3.11+、FFmpeg/FFprobe，并准备当前用户可用的系统密钥环（macOS Keychain，或 Linux Secret Service/GNOME Keyring/KWallet）。

~~~bash
git clone https://github.com/RainyHorizon/voice-studio.git
cd voice-studio
chmod +x start.sh
./start.sh --open-browser
~~~

<code>start.sh</code> 会自动创建 <code>backend/.venv</code>、安装后端依赖并在需要时构建前端。日常启动时，如果已有 <code>frontend/dist</code>，则不需要 Node.js。

### Docker Compose

Docker 部署使用环境变量读取密钥，不会访问宿主机的 Windows Credential Manager、macOS Keychain 或 Linux Secret Service。

~~~bash
git clone https://github.com/RainyHorizon/voice-studio.git
cd voice-studio
cp .env.example .env
~~~

编辑 <code>.env</code>，至少设置一个随机的 <code>VOICE_STUDIO_GATEWAY_KEY</code>，再启动：

~~~bash
docker compose up -d
docker compose ps
docker compose logs -f voice-studio
~~~

默认地址为 <code>http://127.0.0.1:8765</code>，数据保存在项目的 <code>data</code> 目录。停止服务但保留数据：

~~~bash
docker compose down
~~~

如需从源码构建镜像：

~~~bash
docker compose up -d --build
~~~

## 配置厂商账号

启动后进入 **设置**，选择厂商并填写 API Key。Endpoint 通常保持界面预填的官方地址；只有厂商账号或网络环境明确要求时才修改。

桌面版默认使用当前用户的系统密钥环：

| 平台 | 凭据存储 |
| --- | --- |
| Windows | Windows Credential Manager |
| macOS | Keychain |
| Linux | Secret Service（GNOME Keyring/KWallet） |
| Docker | 环境变量或部署平台 Secret |

Docker 支持的变量：

| 变量 | 用途 |
| --- | --- |
| <code>VOICE_STUDIO_GATEWAY_KEY</code> | OpenAI 兼容 API 的 Bearer Key，必填 |
| <code>VOICE_STUDIO_DASHSCOPE_API_KEY</code> | 通义千问 API Key |
| <code>VOICE_STUDIO_VOLCENGINE_API_KEY</code> | 火山引擎语音 API Key |
| <code>VOICE_STUDIO_VOLCENGINE_OPENAPI_ACCESS_KEY</code> | 火山引擎云端音色同步 Access Key |
| <code>VOICE_STUDIO_VOLCENGINE_OPENAPI_SECRET_KEY</code> | 火山引擎云端音色同步 Secret Key |
| <code>VOICE_STUDIO_VOLCENGINE_PROJECT_NAME</code> | 火山引擎项目名称 |
| <code>VOICE_STUDIO_MINIMAX_API_KEY</code> | MiniMax API Key |
| <code>VOICE_STUDIO_MIMO_API_KEY</code> | 小米 MiMo API Key |

火山引擎的语音 API Key 与云端音色同步所需的 Access Key/Secret Key 是两组不同凭据；不需要同步云端音色时，不必填写后两项。修改 <code>.env</code> 后重新执行 <code>docker compose up -d</code> 使配置生效。不要把 <code>.env</code> 提交到 GitHub。

## OpenAI 兼容 API

在 **API 网关** 页面查看 Gateway Key。默认 Base URL：

~~~text
http://127.0.0.1:8765/v1
~~~

| 接口 | 方法 | 用途 |
| --- | --- | --- |
| <code>/v1/models</code> | <code>GET</code> | 查询可用模型 |
| <code>/v1/audio/speech</code> | <code>POST</code> | 生成完整音频文件 |
| <code>/v1/audio/speech/stream</code> | <code>POST</code> | 通过 SSE 接收流式音频分片 |

请求需要携带：

~~~http
Authorization: Bearer <Gateway Key>
~~~

<code>model</code> 可以使用 API 网关页面显示的完整模型 ID，也可以使用 <code>tts-default</code>、<code>tts-fast</code> 或 <code>tts-hq</code>。<code>voice</code> 必须与所选模型兼容。

### Python SDK

~~~python
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
~~~

### Node.js SDK

~~~javascript
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
~~~

普通 OpenAI SDK 客户端使用 <code>/v1/audio/speech</code>。需要边接收边处理音频时，再使用 Voice Studio 的 <code>/v1/audio/speech/stream</code>。

## 音频、历史与存储

| 数据 | 默认位置 |
| --- | --- |
| 生成音频、参考音频 | <code>data/audio</code> |
| 任务、音色和账号元数据 | <code>data/voice_studio.db</code> |
| Docker 数据 | Compose 挂载的 <code>./data</code> |
| 本地 Gateway Key | <code>data/gateway.json</code>（Docker 优先使用环境变量） |

在 **设置 → 存储与清理** 中可以配置自动清理开关、音频保留天数、容量上限和检查周期。建议先在 **任务历史** 中导出需要长期保存的文字与音频，再启用自动清理。删除任务历史只影响本地记录，不会删除厂商云端音色。

PCM 是不带文件头的原始音频数据，浏览器通常无法直接播放。日常使用建议选择 MP3 或 WAV；PCM 适合流式处理或专业音频软件。

## 安全说明

- 厂商 API Key 和火山引擎 AK/SK 默认保存在系统密钥环，不写入 SQLite、前端文件或 Git。
- 页面只显示脱敏后的凭据，不返回完整密钥。
- 服务默认仅监听 <code>127.0.0.1</code>；不要在没有 HTTPS、访问控制和限流的情况下暴露到公网。
- Gateway Key 能调用已配置的付费语音接口，应与厂商 API Key 一样妥善保管。
- Docker 使用 <code>.env</code> 或部署平台 Secret 注入密钥；不要把 <code>.env</code>、数据库、音频或日志提交到 GitHub。
- 自定义 Endpoint 会改变密钥发送目标，没有明确需求时请使用官方预填地址。
- 声音克隆前必须获得声音所有者授权，并遵守相关法律和厂商条款。

## 技术架构

| 层级 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite |
| 后端 | FastAPI、Python |
| 数据 | SQLite、本地音频文件 |
| 厂商连接 | HTTP、WebSocket |
| 兼容接口 | OpenAI 风格 REST API、SSE |
| 部署 | Windows 便携版、跨平台源码启动、Docker Compose |

~~~text
浏览器 / OpenAI 客户端
          │
          ▼
     FastAPI 本地服务
       │          │
       ▼          ▼
  SQLite + 音频   厂商语音 API
~~~

浏览器前端不会直接携带厂商 API Key 请求第三方服务，所有厂商适配、凭据读取和本地文件写入都由后端完成。

## 开发与测试

前端构建：

~~~powershell
Set-Location frontend
npm ci
npm run build
~~~

后端测试：

~~~powershell
Set-Location backend
python -m pip install -r requirements.txt
python -m pip install pytest==8.3.5
python -m pytest -q tests
~~~

测试不会调用真实厂商 API。真实语音测试可能产生费用或消耗额度，请确认账号权限和计费规则后再运行。

## GitHub Actions 与发布

仓库已配置：

| 工作流 | 触发条件 | 作用 |
| --- | --- | --- |
| <code>CI</code> | 推送或 PR 到 <code>main</code> | 三平台测试、前端构建、Docker 构建验证 |
| <code>Build Release Assets</code> | 推送 <code>v*.*.*</code> 标签 | 生成 Windows 轻量 ZIP、macOS/Linux 源码包并创建 Release |
| <code>Publish Docker Image</code> | 推送版本标签，或手动运行 | 发布 <code>linux/amd64</code>、<code>linux/arm64</code> GHCR 镜像 |

发布新版本时，先合并代码到 <code>main</code>，再创建并推送标签：

~~~bash
git tag v0.6.0
git push origin v0.6.0
~~~

GitHub Actions 会自动构建 Windows 轻量版、Windows 便携版（含 <code>.sha256</code> 校验文件）、macOS/Linux 发布包和 Docker 镜像。当前 macOS/Linux 发布包是预构建前端的源码包，不是签名的 <code>.app</code>、<code>.dmg</code> 或 AppImage。

## 当前限制

- 项目主要面向单用户本地运行，不是多租户云服务。
- 厂商可能调整模型名称、接口、计费方式和权限要求。
- 克隆、设计和云端音色同步能力取决于厂商账号、地区、额度和模型权限。
- OpenAI 兼容网关覆盖常用语音接口，不保证覆盖 OpenAI 全部字段。
- Windows 便携版目前未进行商业代码签名，SmartScreen 可能显示“未知发布者”。下载后可使用 Release 提供的 SHA256 文件校验完整性。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。第三方依赖及其许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
