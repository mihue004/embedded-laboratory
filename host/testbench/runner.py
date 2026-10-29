import json
import sys
import time
from datetime import datetime
from pathlib import Path

import serial
import yaml

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "artifacts" / "results"


def wait_for_ready(port, timeout_seconds=8):
    """Warte auf die einmalige Firmware-Startmeldung."""
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        response = port.readline().decode("ascii", errors="replace").strip()

        if response == "READY,TESTBENCH,1":
            return response

    raise TimeoutError(
        "Firmware-Startmeldung READY,TESTBENCH,1 nicht empfangen. "
        "Pico-Verbindung und Neustart prüfen."
    )


def _expect_fields(response, prefix, expected_fields):
    fields = response.split(",")

    if len(fields) != len(expected_fields) + len(prefix):
        raise RuntimeError(f"Unerwartete Antwort: {response}")

    if fields[:len(prefix)] != prefix:
        raise RuntimeError(
            f"Unerwartete Antwort: {response}; erwartet: {','.join(prefix)},..."
        )

    for index, expected in enumerate(
        expected_fields, start=len(prefix)
    ):
        if fields[index] != expected:
            raise RuntimeError(
                f"Unerwartete Antwort: {response}; "
                f"Feld {index + 1} erwartet {expected}"
            )


def execute_step(port, step):
    action = step["action"]
    expected_fields = None
    prefix = None

    if action == "serial.ready":
        response = getattr(port, "_testbench_startup_response", None)
        if response != "READY,TESTBENCH,1":
            raise RuntimeError(
                "Startmeldung wurde nicht zuverlässig erfasst."
            )
        return {
            "action": action,
            "response": response,
            "result": "PASS",
        }

    if action == "gpio.write":
        raw_value = step["value"]

        if isinstance(raw_value, bool):
            value = int(raw_value)
        elif str(raw_value).upper() in ("HIGH", "1"):
            value = 1
        elif str(raw_value).upper() in ("LOW", "0"):
            value = 0
        else:
            raise ValueError(f"Ungültiger GPIO-Wert: {raw_value}")

        pin = int(step["pin_number"])
        command = f"WRITE,{pin},{value}"
        prefix = ["OK", "WRITE"]
        expected_fields = [f"GPIO={pin}", f"VALUE={value}"]

    elif action == "gpio.read":
        pin = int(step["pin_number"])
        command = f"READ,{pin}"

    elif action == "serial.status":
        command = "STATUS"

    elif action == "signal.square":
        pin = int(step["pin_number"])
        frequency = int(step["frequency_hz"])
        duty = int(step["duty_percent"])
        command = f"SIG,{pin},{frequency},{duty}"
        prefix = ["OK", "SIGNAL"]
        expected_fields = [
            f"GPIO={pin}",
            f"FREQ={frequency}",
            f"DUTY={duty}",
        ]

    elif action == "signal.stop":
        command = "STOP"

    elif action == "wait":
        time.sleep(step["duration_ms"] / 1000)
        return {
            "action": action,
            "result": "PASS",
            "response": "WAITED",
        }

    else:
        raise ValueError(f"Unbekannte Aktion: {action}")

    port.reset_input_buffer()
    port.write((command + "\n").encode("ascii"))
    port.flush()

    response = port.readline().decode("ascii", errors="replace").strip()

    if not response:
        raise TimeoutError(f"Keine Antwort auf: {command}")

    if response.startswith("ERR,"):
        raise RuntimeError(f"{command} -> {response}")

    if action == "gpio.read":
        fields = response.split(",")

        if len(fields) != 3 or fields[0] != "VALUE":
            raise RuntimeError(f"Unerwartete Antwort: {response}")

        try:
            actual_pin = int(fields[1])
            actual_value = int(fields[2])
            expected = int(step["expect_value"])
        except (ValueError, TypeError) as error:
            raise RuntimeError(
                f"Ungültige GPIO-Leseantwort: {response}"
            ) from error

        if actual_pin != pin:
            raise RuntimeError(
                f"Falscher GPIO zurückgemeldet: erwartet {pin}, "
                f"erhalten {actual_pin}"
            )

        if actual_value not in (0, 1):
            raise RuntimeError(f"Ungültiger GPIO-Wert: {actual_value}")

        if actual_value != expected:
            raise AssertionError(
                f"GPIO {pin}: erwartet {expected}, erhalten {actual_value}"
            )

    elif action == "gpio.write":
        _expect_fields(response, prefix, expected_fields)

    elif action == "serial.status":
        fields = response.split(",")
        if len(fields) != 5 or fields[0] != "STATUS":
            raise RuntimeError(f"Unerwartete STATUS-Antwort: {response}")

        parsed = {}
        for field in fields[1:]:
            if "=" not in field:
                raise RuntimeError(f"Ungültige STATUS-Antwort: {response}")
            key, value = field.split("=", 1)
            if key in parsed:
                raise RuntimeError(f"Doppeltes STATUS-Feld: {key}")
            parsed[key] = value

        if set(parsed) != {"ACTIVE", "GPIO", "FREQ", "DUTY"}:
            raise RuntimeError(f"Ungültige STATUS-Felder: {response}")

        if parsed["ACTIVE"] not in {"0", "1"}:
            raise RuntimeError(f"Ungültiger ACTIVE-Wert: {response}")

        expected_active = str(int(step["expect_active"]))
        if parsed["ACTIVE"] != expected_active:
            raise AssertionError(
                f"STATUS ACTIVE: erwartet {expected_active}, "
                f"erhalten {parsed['ACTIVE']}"
            )

        try:
            int(parsed["GPIO"])
            int(parsed["FREQ"])
            int(parsed["DUTY"])
        except ValueError as error:
            raise RuntimeError(
                f"Ungültige numerische STATUS-Felder: {response}"
            ) from error

    elif action == "signal.square":
        _expect_fields(response, prefix, expected_fields)

    elif action == "signal.stop":
        if response != "OK,STOPPED":
            raise RuntimeError(f"Unerwartete Antwort auf STOP: {response}")

    return {
        "action": action,
        "command": command,
        "response": response,
        "result": "PASS",
    }


def main():
    if len(sys.argv) != 3:
        print("Verwendung: python runner.py TESTDATEI.yaml SERIELLER_PORT")
        sys.exit(2)

    test_path = Path(sys.argv[1]).resolve()
    port_name = sys.argv[2]

    with test_path.open(encoding="utf-8") as file:
        test_case = yaml.safe_load(file)

    RESULTS.mkdir(parents=True, exist_ok=True)

    report = {
        "test": test_case.get("name", test_path.stem),
        "started": datetime.now().astimezone().isoformat(),
        "steps": [],
        "result": "PASS",
    }

    try:
        with serial.Serial(port_name, 115200, timeout=1) as port:
            ready = wait_for_ready(port)
            port._testbench_startup_response = ready
            report["startup_response"] = ready
            print(f"[PASS] Firmware bereit: {ready}")

            for index, step in enumerate(test_case["steps"], start=1):
                try:
                    result = execute_step(port, step)
                    report["steps"].append(result)
                    print(f"[PASS] Schritt {index}: {step['action']}")

                except Exception as error:
                    report["steps"].append({
                        "action": step.get("action"),
                        "result": "FAIL",
                        "error": str(error),
                    })
                    report["result"] = "FAIL"
                    print(f"[FAIL] Schritt {index}: {error}")
                    break

    except Exception as error:
        report["result"] = "FAIL"
        report["error"] = str(error)
        print(f"[FAIL] Testausführung: {error}")

    report["finished"] = datetime.now().astimezone().isoformat()

    filename = (
        datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + test_path.stem
        + ".json"
    )
    output = RESULTS / filename
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Gesamtergebnis: {report['result']}")
    print(f"Bericht: {output}")

    if report["result"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
