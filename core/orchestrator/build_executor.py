"""Controlled project build execution for Embedded Lab."""

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from orchestrator import load_yaml, resolve_inside_project
from validate_project import validate_project


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "project.schema.yaml"
SAFE_CMAKE_OPTION = re.compile(
    r"^-D[A-Za-z_][A-Za-z0-9_]*=[A-Za-z0-9_./:+-]*$"
)


def _result(project_root: Path, status: str, message: str) -> dict:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_dir": str(project_root),
        "status": status,
        "execution_performed": False,
        "commands": [],
        "errors": [message] if message else [],
        "report_path": None,
    }


def _save_report(report: dict, reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        "build-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + ".json"
    )
    report_path = reports_dir / filename
    report["report_path"] = str(report_path)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _run_command(command: list[str], *, output_callback=None, **kwargs):
    """Run a command while capturing and optionally streaming both output streams."""
    from queue import Empty, Queue
    from threading import Thread

    timeout = kwargs.pop("timeout", None)
    kwargs.pop("capture_output", None)
    kwargs.pop("check", None)
    kwargs["stdout"] = subprocess.PIPE
    kwargs["stderr"] = subprocess.PIPE
    kwargs.setdefault("text", True)
    kwargs.setdefault("bufsize", 1)

    process = subprocess.Popen(command, **kwargs)
    events = Queue()
    output = {"stdout": [], "stderr": []}

    def read_stream(name, stream):
        try:
            for line in iter(stream.readline, ""):
                events.put((name, line))
        finally:
            stream.close()
            events.put((name, None))

    threads = [
        Thread(target=read_stream, args=("stdout", process.stdout), daemon=True),
        Thread(target=read_stream, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout if timeout is not None else None
    closed_streams = set()
    timed_out = False

    while len(closed_streams) < 2:
        if deadline is not None and time.monotonic() >= deadline:
            if process.poll() is None:
                timed_out = True
                process.kill()

        try:
            name, line = events.get(timeout=0.05)
        except Empty:
            continue

        if line is None:
            closed_streams.add(name)
            continue

        output[name].append(line)
        if output_callback is not None:
            output_callback(name, line)

    returncode = process.wait()
    for thread in threads:
        thread.join()

    stdout = "".join(output["stdout"])
    stderr = "".join(output["stderr"])

    if timed_out:
        raise subprocess.TimeoutExpired(
            command, timeout, output=stdout, stderr=stderr
        )

    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def execute_build(
    project_dir: Path,
    *,
    approved: bool = False,
    timeout_seconds: int = 600,
    output_callback=None,
    event_callback=None
) -> dict:
    """Build a validated project only after explicit caller approval.

    Commands are passed as argument lists, never through a shell.
    This function does not flash firmware or run tests.
    """
    project_root = project_dir.expanduser().resolve()

    if approved is not True:
        return _result(
            project_root,
            "blocked",
            "Build requires explicit approval.",
        )

    if not project_root.is_dir():
        return _result(
            project_root,
            "error",
            f"Project directory does not exist: {project_root}",
        )

    config_path = project_root / "project.yaml"
    if not config_path.is_file():
        return _result(
            project_root,
            "error",
            f"Missing project contract: {config_path}",
        )

    schema_errors = validate_project(config_path, SCHEMA)
    if schema_errors:
        report = _result(
            project_root,
            "error",
            "Invalid project contract: " + "; ".join(schema_errors),
        )
        return report

    try:
        config = load_yaml(config_path)
        build_config = config["build"]
        source_dir = resolve_inside_project(
            project_root, build_config["source_dir"]
        )
        build_dir = resolve_inside_project(
            project_root, build_config["build_dir"]
        )
        reports_dir = resolve_inside_project(
            project_root, config["artifacts"]["reports_directory"]
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return _result(
            project_root,
            "error",
            f"Invalid build configuration or path: {exc}",
        )

    if not source_dir.is_dir():
        return _result(
            project_root,
            "error",
            f"Build source directory does not exist: {source_dir}",
        )

    system = build_config["system"]
    options = build_config.get("options", [])

    # Das Pico-SDK liegt außerhalb der importierten Projektverzeichnisse.
    # Der Pfad ist konfigurierbar und wird niemals aus Projektdateien ausgeführt.
    pico_sdk_arg = None
    pico_board_arg = None
    target = config.get("target", {})
    if target.get("platform") == "pico-sdk":
        board = target.get("board")
        controller = target.get("controller")
        known_boards = {
            "pico": "RP2040",
            "pico_w": "RP2040",
            "pico2": "RP2350",
            "pico2_w": "RP2350",
        }

        if not isinstance(board, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]+", board
        ):
            return _result(
                project_root,
                "error",
                "Pico-SDK-Projekte benötigen einen gültigen target.board-Wert.",
            )

        expected_controller = known_boards.get(board)
        if expected_controller and controller != expected_controller:
            return _result(
                project_root,
                "error",
                f"Board {board} erwartet Controller {expected_controller}, "
                f"konfiguriert ist {controller!r}.",
            )

        pico_board_arg = f"-DPICO_BOARD={board}"

        sdk_path = Path(
            os.environ.get(
                "EMBEDDED_LAB_PICO_SDK",
                str(ROOT / "pico-sdk"),
            )
        ).expanduser().resolve()

        if not (sdk_path / "external" / "pico_sdk_import.cmake").is_file():
            return _result(
                project_root,
                "error",
                "Pico-SDK nicht gefunden oder unvollständig: "
                f"{sdk_path}. Setze EMBEDDED_LAB_PICO_SDK auf das SDK-Verzeichnis.",
            )

        pico_sdk_arg = f"-DPICO_SDK_PATH={sdk_path}"

        # Einen vorhandenen Cache für ein anderes Target niemals still nutzen.
        cache_file = build_dir / "CMakeCache.txt"
        if cache_file.is_file():
            cache_text = cache_file.read_text(
                encoding="utf-8", errors="replace"
            )
            cached = {}
            for line in cache_text.splitlines():
                match = re.match(
                    r"^(PICO_BOARD|PICO_PLATFORM):[^=]*=(.*)$", line
                )
                if match:
                    cached[match.group(1)] = match.group(2).strip()

            expected_platforms = {
                "pico": "rp2040",
                "pico_w": "rp2040",
                "pico2": "rp2350-arm-s",
                "pico2_w": "rp2350-arm-s",
            }
            mismatches = []
            cached_board = cached.get("PICO_BOARD")
            if cached_board and cached_board != board:
                mismatches.append(
                    f"Board im Cache: {cached_board}, Projekt: {board}"
                )

            expected_platform = expected_platforms.get(board)
            cached_platform = cached.get("PICO_PLATFORM")
            if (
                expected_platform
                and cached_platform
                and cached_platform != expected_platform
            ):
                mismatches.append(
                    f"Plattform im Cache: {cached_platform}, "
                    f"erwartet: {expected_platform}"
                )

            if mismatches:
                return _result(
                    project_root,
                    "error",
                    "Inkompatibler CMake-Cache. " + "; ".join(mismatches)
                    + ". Verwende einen neuen build_dir; der bestehende "
                    "Cache wurde nicht verändert.",
                )

    if system == "cmake":
        if any(
            not isinstance(option, str)
            or not SAFE_CMAKE_OPTION.fullmatch(option)
            for option in options
        ):
            return _result(
                project_root,
                "error",
                "Unsafe or unsupported CMake option. "
                "Only -DNAME=VALUE options with simple values are allowed.",
            )
        executable = shutil.which("cmake")
        if not executable:
            return _result(project_root, "error", "CMake is not installed.")

        commands = [
            [
                executable, "-S", str(source_dir),
                "-B", str(build_dir), "-G", "Ninja",
                *options,
                *([pico_sdk_arg] if pico_sdk_arg else []),
                *([pico_board_arg] if pico_board_arg else []),
            ],
            [
                executable, "--build", str(build_dir),
                "--parallel", "2",
            ],
        ]
    elif system == "make":
        if options:
            return _result(
                project_root,
                "error",
                "Build options are not yet supported for Make projects.",
            )
        executable = shutil.which("make")
        if not executable:
            return _result(project_root, "error", "Make is not installed.")
        commands = [[executable, "-C", str(source_dir)]]
    elif system == "platformio":
        if options:
            return _result(
                project_root,
                "error",
                "Build options are not yet supported for PlatformIO projects.",
            )
        executable = shutil.which("pio")
        if not executable:
            return _result(
                project_root,
                "error",
                "PlatformIO is not installed (missing 'pio' executable).",
            )
        commands = [[executable, "run", "-d", str(source_dir)]]
    else:
        return _result(
            project_root,
            "error",
            f"Unsupported build system: {system}",
        )

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds < 1
    ):
        return _result(
            project_root,
            "error",
            "timeout_seconds must be a positive integer.",
        )

    report = _result(project_root, "running", "")
    report["execution_performed"] = True
    report["build_system"] = system
    report["timeout_seconds"] = timeout_seconds
    started = time.monotonic()

    for command in commands:
        entry = {
            "argv": command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "duration_seconds": 0,
            "status": "running",
        }
        command_started = time.monotonic()
        command_index = len(report["commands"])

        if event_callback is not None:
            event_callback({
                "type": "command_started",
                "command_index": command_index,
                "argv": command,
                "status": "running",
            })

        def on_command_output(stream, line):
            if output_callback is not None:
                output_callback(stream, line)
            if event_callback is not None:
                event_callback({
                    "type": "command_output",
                    "command_index": command_index,
                    "stream": stream,
                    "line": line,
                })

        try:
            completed = _run_command(
                command,
                cwd=str(project_root),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                output_callback=on_command_output,
            )
            entry["returncode"] = completed.returncode
            entry["stdout"] = completed.stdout
            entry["stderr"] = completed.stderr
            entry["status"] = (
                "passed" if completed.returncode == 0 else "failed"
            )
        except subprocess.TimeoutExpired as exc:
            entry["status"] = "timeout"
            entry["stdout"] = (
                exc.stdout.decode(errors="replace")
                if isinstance(exc.stdout, bytes)
                else exc.stdout or ""
            )
            entry["stderr"] = (
                exc.stderr.decode(errors="replace")
                if isinstance(exc.stderr, bytes)
                else exc.stderr or ""
            )
            report["errors"].append(
                f"Build command exceeded {timeout_seconds} seconds."
            )
        except OSError as exc:
            entry["status"] = "error"
            entry["stderr"] = str(exc)
            report["errors"].append(f"Could not start build command: {exc}")

        entry["duration_seconds"] = round(
            time.monotonic() - command_started, 3
        )
        report["commands"].append(entry)

        if event_callback is not None:
            event_callback({
                "type": "command_finished",
                "command_index": command_index,
                "status": entry["status"],
                "returncode": entry["returncode"],
                "stdout": entry["stdout"],
                "stderr": entry["stderr"],
                "duration_seconds": entry["duration_seconds"],
            })

        if entry["status"] != "passed":
            if entry["status"] == "failed":
                report["errors"].append(
                    f"Build command exited with code {entry['returncode']}."
                )
            elif entry["status"] == "error":
                pass
            report["status"] = "failed"
            break

    if report["status"] == "running":
        report["status"] = "passed"

    report["duration_seconds"] = round(time.monotonic() - started, 3)
    report["flash_performed"] = False
    report["tests_executed"] = False

    try:
        _save_report(report, reports_dir)
    except OSError as exc:
        report["errors"].append(f"Could not save build report: {exc}")
        report["status"] = "failed"

    return report
