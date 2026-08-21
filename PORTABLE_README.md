# Voice Studio Windows 便携版

## 使用方法

1. 将压缩包完整解压到普通文件夹，不要直接在压缩包预览窗口中运行。
2. 双击 `启动 Voice Studio.bat`。
3. 等待浏览器自动打开 Voice Studio。
4. 使用期间不要关闭启动窗口；关闭窗口即可停止服务。

便携版已包含 Python 运行时、后端依赖、前端文件、FFmpeg 和 FFprobe，不需要另外安装 Python、Node.js 或 FFmpeg。

## 数据位置

数据库、生成音频和网关配置保存在程序目录的 `data` 文件夹。升级时请保留这个文件夹，卸载时可以直接删除整个程序目录。

厂商 API Key、火山引擎 AK/SK 仍保存在当前 Windows 用户的 Credential Manager 中，不会写入程序目录。

## 常见问题

- 如果 Windows 提示来源未知，请先确认文件来自本项目的 GitHub Releases 页面。当前版本尚未进行商业代码签名。
- 如果程序目录不可写，请将整个文件夹移动到桌面、文档或其他普通目录，不要放在 `Program Files` 中。
- 如果默认端口 `8765` 被占用，程序会自动尝试 `8766` 至 `8790`。
- 需要查看完整诊断时，在 PowerShell 中运行 `.\VoiceStudio.exe --check`。

完整项目文档请查看 `README.md`。
