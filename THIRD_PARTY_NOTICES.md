# Third-party notices

Voice Studio 的 Windows 便携版包含以下第三方组件。Voice Studio 自身仍按照仓库根目录中的 MIT License 发布。

## FFmpeg

- Project: FFmpeg
- Website: https://ffmpeg.org/
- Windows build provider: https://www.gyan.dev/ffmpeg/builds/
- License: GNU General Public License version 3 or later（以便携包内 `third_party/ffmpeg/LICENSE` 为准）
- Source code: https://ffmpeg.org/download.html#get-sources

FFmpeg 与 Voice Studio 作为独立程序一同分发，Voice Studio 通过命令行调用 `ffmpeg.exe` 和 `ffprobe.exe`。

构建便携包时使用的 FFmpeg 版本和构建配置记录在 `third_party/ffmpeg/README.txt` 中。重新分发便携包时，请同时保留该目录中的许可证与说明文件。
