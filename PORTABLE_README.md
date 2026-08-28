# Voice Studio Windows 便携版

## 使用方法

1. 将压缩包完整解压到普通文件夹，不要直接在压缩包预览窗口中运行。
2. 双击 `启动 Voice Studio.bat`。
3. 等待浏览器自动打开 Voice Studio。
4. 使用期间不要关闭启动窗口；也可以双击 `停止 Voice Studio.bat` 停止服务。

## 更新

1. 先关闭正在运行的 Voice Studio。
2. 双击 `更新 Voice Studio.bat`。
3. 确认显示的当前版本和 GitHub 最新正式版本，输入 `Y` 开始更新。
4. 更新完成后可直接选择重新启动。

更新器会自动识别当前的 Windows 安装方式。便携版只从 `RainyHorizon/voice-studio` 的 GitHub Releases 下载 Windows Portable 版本，并在替换程序前验证 SHA256。`data` 文件夹、Windows Credential Manager 中的厂商密钥以及目录内其他非程序文件不会被删除。

首次获得更新器之前安装的旧版本，仍需手动下载一次包含更新器的新便携版；以后即可使用这个入口更新。

便携版已包含 Python 运行时、后端依赖、前端文件、FFmpeg 和 FFprobe，不需要另外安装 Python、Node.js 或 FFmpeg。

## 数据位置

数据库、生成音频和网关配置保存在程序目录的 `data` 文件夹。自动更新会保留这个文件夹；手动升级时也请保留它。卸载时可以直接删除整个程序目录。

厂商 API Key、火山引擎 AK/SK 仍保存在当前 Windows 用户的 Credential Manager 中，不会写入程序目录。

## 常见问题

- 如果 Windows 提示来源未知，请先确认文件来自本项目的 GitHub Releases 页面。当前版本尚未进行商业代码签名。
- 如果程序目录不可写，请将整个文件夹移动到桌面、文档或其他普通目录，不要放在 `Program Files` 中。
- 如果默认端口 `8765` 被占用，程序会自动尝试 `8766` 至 `8790`。
- 需要查看完整诊断时，在 PowerShell 中运行 `.\VoiceStudio.exe --check`。

完整项目文档请查看 `README.md`。
