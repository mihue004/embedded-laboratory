import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_executor import execute_build


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "pico-sdk"


class TestBuildExecutor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.project = Path(self.temp_dir.name) / "test-project"
        shutil.copytree(TEMPLATE, self.project)

    def test_build_is_blocked_without_explicit_approval(self):
        with patch("build_executor._run_command") as run:
            result = execute_build(self.project)

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["execution_performed"])
        run.assert_not_called()

    def test_missing_project_is_rejected(self):
        result = execute_build(self.project / "missing", approved=True)

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["execution_performed"])

    def test_missing_contract_is_rejected(self):
        (self.project / "project.yaml").unlink()

        result = execute_build(self.project, approved=True)

        self.assertEqual(result["status"], "error")
        self.assertIn("Missing project contract", result["errors"][0])

    def test_invalid_timeout_is_rejected_without_execution(self):
        with patch("build_executor._run_command") as run:
            result = execute_build(
                self.project, approved=True, timeout_seconds=0
            )

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["execution_performed"])
        run.assert_not_called()

    def test_unsafe_cmake_option_is_rejected(self):
        import yaml

        config_path = self.project / "project.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["build"]["options"] = ["-DNAME=value;touch /tmp/unwanted"]
        config_path.write_text(
            yaml.safe_dump(config, sort_keys=False),
            encoding="utf-8",
        )

        with patch("build_executor._run_command") as run:
            result = execute_build(self.project, approved=True)

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["execution_performed"])
        run.assert_not_called()

    def test_mismatched_pico_board_and_controller_blocks_execution(self):
        import yaml

        config_path = self.project / "project.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["target"]["board"] = "pico"
        config["target"]["controller"] = "RP2350"
        config_path.write_text(
            yaml.safe_dump(config, sort_keys=False),
            encoding="utf-8",
        )

        with patch("build_executor._run_command") as run:
            result = execute_build(self.project, approved=True)

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["execution_performed"])
        self.assertIn("erwartet Controller RP2040", result["errors"][0])
        run.assert_not_called()

    def test_incompatible_pico_cache_blocks_execution(self):
        import yaml

        config_path = self.project / "project.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["build"]["build_dir"] = "build"
        config_path.write_text(
            yaml.safe_dump(config, sort_keys=False),
            encoding="utf-8",
        )

        build_dir = self.project / "build"
        build_dir.mkdir()
        (build_dir / "CMakeCache.txt").write_text(
            "PICO_BOARD:STRING=pico\\n"
            "PICO_PLATFORM:STRING=rp2040\\n",
            encoding="utf-8",
        )

        with patch("build_executor._run_command") as run:
            result = execute_build(self.project, approved=True)

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["execution_performed"])
        self.assertIn("Inkompatibler CMake-Cache", result["errors"][0])
        run.assert_not_called()

    def test_successful_cmake_build_is_mocked_and_reported(self):
        from types import SimpleNamespace

        with (
            patch("build_executor.shutil.which", return_value="/usr/bin/cmake"),
            patch(
                "build_executor._run_command",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout="build ok",
                    stderr="",
                ),
            ) as run,
        ):
            result = execute_build(self.project, approved=True)

        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["execution_performed"])
        self.assertFalse(result["flash_performed"])
        self.assertFalse(result["tests_executed"])
        self.assertEqual(len(result["commands"]), 2)
        self.assertEqual(run.call_count, 2)

        configure_argv = run.call_args_list[0].args[0]
        expected_sdk = (ROOT / "pico-sdk").resolve()
        self.assertIn(f"-DPICO_SDK_PATH={expected_sdk}", configure_argv)
        self.assertIn("-DPICO_BOARD=pico2", configure_argv)

        report_path = Path(result["report_path"])
        self.assertTrue(report_path.is_file())

        import json
        saved_report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_report["report_path"], str(report_path))
        self.assertEqual(saved_report["status"], "passed")

        for call in run.call_args_list:
            self.assertIs(call.kwargs["shell"], False)
            self.assertEqual(call.kwargs["timeout"], 600)

    def test_timeout_marks_command_and_emits_finished_event(self):
        import subprocess

        events = []
        with (
            patch("build_executor.shutil.which", return_value="/usr/bin/cmake"),
            patch(
                "build_executor._run_command",
                side_effect=subprocess.TimeoutExpired(
                    cmd=["cmake"], timeout=600,
                    output="partial output", stderr="partial error",
                ),
            ) as run,
        ):
            result = execute_build(
                self.project, approved=True, event_callback=events.append
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["status"], "timeout")
        self.assertIn("partial output", result["commands"][0]["stdout"])
        self.assertIn("Build command exceeded 600 seconds", result["errors"][0])
        run.assert_called_once()
        self.assertEqual(events[-1]["type"], "command_finished")
        self.assertEqual(events[-1]["status"], "timeout")

    def test_process_start_error_is_reported_and_emits_finished_event(self):
        events = []
        with (
            patch("build_executor.shutil.which", return_value="/usr/bin/cmake"),
            patch(
                "build_executor._run_command",
                side_effect=OSError("simulierter Prozessstartfehler"),
            ) as run,
        ):
            result = execute_build(
                self.project, approved=True, event_callback=events.append
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["status"], "error")
        self.assertIn(
            "simulierter Prozessstartfehler",
            result["commands"][0]["stderr"],
        )
        self.assertTrue(any(
            "Could not start build command" in error
            for error in result["errors"]
        ))
        run.assert_called_once()
        self.assertEqual(events[-1]["type"], "command_finished")
        self.assertEqual(events[-1]["status"], "error")

    def test_failed_configure_stops_before_build(self):
        from types import SimpleNamespace

        with (
            patch("build_executor.shutil.which", return_value="/usr/bin/cmake"),
            patch(
                "build_executor._run_command",
                return_value=SimpleNamespace(
                    returncode=1,
                    stdout="",
                    stderr="configure failed",
                ),
            ) as run,
        ):
            result = execute_build(self.project, approved=True)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["commands"]), 1)
        run.assert_called_once()

    def test_missing_pico_sdk_blocks_build(self):
        from unittest.mock import patch

        with (
            patch.dict(
                "build_executor.os.environ",
                {"EMBEDDED_LAB_PICO_SDK": "/tmp/embedded-lab-sdk-does-not-exist"},
            ),
            patch("build_executor._run_command") as run,
        ):
            result = execute_build(self.project, approved=True)

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["execution_performed"])
        self.assertIn("Pico-SDK nicht gefunden", result["errors"][0])
        run.assert_not_called()

    def test_missing_platformio_is_reported(self):
        import yaml

        config_path = self.project / "project.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["build"]["system"] = "platformio"
        config["build"]["options"] = []
        config_path.write_text(
            yaml.safe_dump(config, sort_keys=False),
            encoding="utf-8",
        )

        with patch("build_executor.shutil.which", return_value=None):
            result = execute_build(self.project, approved=True)

        self.assertEqual(result["status"], "error")
        self.assertIn("PlatformIO is not installed", result["errors"][0])
        self.assertFalse(result["execution_performed"])


if __name__ == "__main__":
    unittest.main()
