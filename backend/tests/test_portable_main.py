from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import portable_main


class PortablePortTests(unittest.TestCase):
    @patch("portable_main.port_is_available", side_effect=lambda port: port == 8766)
    @patch("portable_main.voice_studio_is_running", return_value=False)
    def test_select_port_uses_first_available_fallback(self, _running, _available):
        self.assertEqual(portable_main.select_port(None), (8766, False))

    @patch("portable_main.port_is_available", return_value=False)
    @patch("portable_main.voice_studio_is_running", return_value=True)
    def test_select_port_reuses_running_voice_studio(self, _running, _available):
        self.assertEqual(portable_main.select_port(8765), (8765, True))

    @patch("portable_main.port_is_available", return_value=False)
    @patch("portable_main.voice_studio_is_running", return_value=False)
    def test_explicit_busy_port_is_rejected(self, _running, _available):
        with self.assertRaisesRegex(RuntimeError, "端口 9000 已被其他程序占用"):
            portable_main.select_port(9000)


class PortableEnvironmentTests(unittest.TestCase):
    def test_prepare_environment_uses_bundled_tools_and_data_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for relative in ("tools/ffmpeg.exe", "tools/ffprobe.exe", "frontend/dist/index.html"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

            old_root = os.environ.get("VOICE_STUDIO_ROOT")
            old_port = os.environ.get("VOICE_STUDIO_PORT")
            old_path = os.environ.get("PATH")
            try:
                portable_main.prepare_environment(root, 8877)
                self.assertEqual(os.environ["VOICE_STUDIO_ROOT"], str(root))
                self.assertEqual(os.environ["VOICE_STUDIO_PORT"], "8877")
                self.assertEqual(os.environ["PATH"].split(os.pathsep, 1)[0], str(root / "tools"))
                self.assertTrue((root / "data").is_dir())
            finally:
                if old_root is None:
                    os.environ.pop("VOICE_STUDIO_ROOT", None)
                else:
                    os.environ["VOICE_STUDIO_ROOT"] = old_root
                if old_port is None:
                    os.environ.pop("VOICE_STUDIO_PORT", None)
                else:
                    os.environ["VOICE_STUDIO_PORT"] = old_port
                if old_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = old_path

    def test_prepare_environment_reports_missing_bundle_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(RuntimeError, r"tools[\\/]ffmpeg\.exe"):
                portable_main.prepare_environment(Path(temp_dir), 8877)


if __name__ == "__main__":
    unittest.main()
