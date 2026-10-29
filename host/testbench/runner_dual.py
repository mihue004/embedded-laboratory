import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import serial
import yaml

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "artifacts" / "results"

DEFAULT_GENERATOR = (
    "/dev/serial/by-id/"
    "usb-Raspberry_Pi_Pico_5656C13DD120BFED-if00"
)
DEFAULT_ANALYZER = (
    "/dev/serial/by-id/"
    "usb-Raspberry_Pi_Pico_FF9668AFF1801C9A-if00"
)


def read_line(port, timeout_s=3):
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        line = port.readline().decode("ascii", errors="replace").strip()
        if line:
            return line

    raise TimeoutError(f"Keine Antwort von {port.port} innerhalb {timeout_s}s")


def command(port, text, expected_prefix, timeout_s=3):
    port.write((text + "\n").encode("ascii"))
    port.flush()

    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        line = port.readline().decode("ascii", errors="replace").strip()

        if not line:
            continue

        print(f"  [{port.port}] {line}")

        if line.startswith("ERR,"):
            raise RuntimeError(f"{text} -> {line}")

        if line.startswith(expected_prefix):
            return line

    raise TimeoutError(
        f"Keine Antwort mit Präfix {expected_prefix!r} "
        f"auf {text!r} von {port.port}"
    )


def parse_measurement(line):
    values = {}

    for key, value in re.findall(r"([A-Z_]+)=([0-9.]+)", line):
        values[key] = float(value)

    required = ("FREQ_HZ", "DUTY", "PERIOD_US", "HIGH_US")
    missing = [key for key in required if key not in values]

    if missing:
        raise ValueError(f"Messdatensatz unvollständig: {line}")

    return values


def run_signal_test(generator, analyzer, step):
    pin_out = int(step.get("generator_pin", 15))
    pin_in = int(step.get("analyzer_pin", 16))
    frequency = int(step["frequency_hz"])
    duty = int(step["duty_percent"])

    frequency_tolerance = float(
        step.get("frequency_tolerance_percent", 3.0)
    )
    duty_tolerance = float(step.get("duty_tolerance_percent", 5.0))
    settle_ms = int(step.get("settle_ms", 150))

    if not 1 <= frequency <= 10000:
        raise ValueError("Generator-Frequenz muss derzeit 1 bis 10000 Hz sein")
    if not 1 <= duty <= 99:
        raise ValueError("Tastgrad muss zwischen 1 und 99 Prozent liegen")

    result = {
        "action": "signal.measure",
        "generator_pin": pin_out,
        "analyzer_pin": pin_in,
        "expected_frequency_hz": frequency,
        "expected_duty_percent": duty,
        "frequency_tolerance_percent": frequency_tolerance,
        "duty_tolerance_percentage_points": duty_tolerance,
    }

    try:
        # Sicherstellen, dass der Analyzer den vorgesehenen Eingang nutzt.
        command(analyzer, f"CONFIG,{pin_in}", "OK,CONFIG")

        # Signal starten und auf die Antwort des Generators warten.
        command(
            generator,
            f"SIG,{pin_out},{frequency},{duty}",
            "OK,SIGNAL",
        )

        # Einschwingzeit, damit die Messung nicht beim Umschalten beginnt.
        time.sleep(settle_ms / 1000.0)

        # Eine Messung anfordern und den nächsten Messdatensatz abwarten.
        analyzer.write(b"MEASURE\n")
        analyzer.flush()

        deadline = time.monotonic() + max(3.0, 2.0 / frequency + 1.0)
        measurement_line = None

        while time.monotonic() < deadline:
            line = analyzer.readline().decode(
                "ascii", errors="replace"
            ).strip()

            if not line:
                continue

            print(f"  [{analyzer.port}] {line}")

            if line.startswith("ERR,"):
                raise RuntimeError(f"Analyzer: {line}")

            if line.startswith("MEASURE,"):
                measurement_line = line
                break

        if measurement_line is None:
            raise TimeoutError("Analyzer hat keinen Messdatensatz geliefert")

        measured = parse_measurement(measurement_line)

        frequency_error_percent = (
            abs(measured["FREQ_HZ"] - frequency) / frequency * 100.0
        )
        duty_error = abs(measured["DUTY"] - duty)

        frequency_pass = frequency_error_percent <= frequency_tolerance
        duty_pass = duty_error <= duty_tolerance

        result.update({
            "measured": measured,
            "frequency_error_percent": round(frequency_error_percent, 3),
            "duty_error_percentage_points": round(duty_error, 3),
            "frequency_result": "PASS" if frequency_pass else "FAIL",
            "duty_result": "PASS" if duty_pass else "FAIL",
            "result": "PASS" if frequency_pass and duty_pass else "FAIL",
        })

        if result["result"] == "FAIL":
            result["error"] = (
                f"Frequenzfehler {frequency_error_percent:.2f}% "
                f"(Toleranz {frequency_tolerance:.2f}%), "
                f"Tastgradabweichung {duty_error:.2f} Prozentpunkte "
                f"(Toleranz {duty_tolerance:.2f})"
            )

        return result

    finally:
        # Auch bei fehlgeschlagener Messung den Generator stoppen.
        try:
            command(generator, "STOP", "OK,STOPPED")
        except Exception as error:
            print(f"  WARNUNG: Generator konnte nicht gestoppt werden: {error}")


def main():
    if len(sys.argv) not in (2, 4):
        print(
            "Verwendung:\n"
            "  python runner_dual.py TESTDATEI.yaml\n"
            "  python runner_dual.py TESTDATEI.yaml GENERATOR_PORT ANALYZER_PORT"
        )
        sys.exit(2)

    test_path = Path(sys.argv[1]).resolve()
    generator_port = sys.argv[2] if len(sys.argv) == 4 else DEFAULT_GENERATOR
    analyzer_port = sys.argv[3] if len(sys.argv) == 4 else DEFAULT_ANALYZER

    with test_path.open(encoding="utf-8") as file:
        test_case = yaml.safe_load(file)

    RESULTS.mkdir(parents=True, exist_ok=True)

    report = {
        "test": test_case.get("name", test_path.stem),
        "description": test_case.get("description", ""),
        "started": datetime.now().astimezone().isoformat(),
        "generator_port": generator_port,
        "analyzer_port": analyzer_port,
        "steps": [],
        "result": "PASS",
    }

    generator = None
    analyzer = None

    try:
        generator = serial.Serial(generator_port, 115200, timeout=0.1)
        analyzer = serial.Serial(analyzer_port, 115200, timeout=0.1)

        time.sleep(2)
        generator.reset_input_buffer()
        analyzer.reset_input_buffer()

        # Vorhandene Firmware-Versionen und Verbindungen prüfen.
        command(generator, "STATUS", "STATUS")
        command(analyzer, "STATUS", "STATUS")

        for index, step in enumerate(test_case["steps"], start=1):
            print(f"\nTest {index}/{len(test_case['steps'])}: {step}")

            try:
                action = step["action"]

                if action == "signal.measure":
                    result = run_signal_test(generator, analyzer, step)
                elif action == "wait":
                    duration_ms = int(step["duration_ms"])
                    time.sleep(duration_ms / 1000.0)
                    result = {
                        "action": action,
                        "duration_ms": duration_ms,
                        "result": "PASS",
                    }
                else:
                    raise ValueError(f"Unbekannte Aktion: {action}")

                report["steps"].append(result)
                print(f"  Ergebnis: {result['result']}")

                if result["result"] != "PASS":
                    report["result"] = "FAIL"

            except Exception as error:
                report["steps"].append({
                    "action": step.get("action"),
                    "result": "FAIL",
                    "error": str(error),
                })
                report["result"] = "FAIL"
                print(f"  FEHLER: {error}")

                # Nach einem Kommunikationsfehler nicht blind weitertesten.
                if isinstance(error, (serial.SerialException, TimeoutError)):
                    break

    except Exception as error:
        report["result"] = "FAIL"
        report["error"] = str(error)
        print(f"\nFEHLER bei der Testausführung: {error}")

    finally:
        if generator is not None and generator.is_open:
            try:
                generator.write(b"STOP\n")
                generator.flush()
                time.sleep(0.1)
            except Exception:
                pass
            generator.close()

        if analyzer is not None and analyzer.is_open:
            analyzer.close()

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

    passed = sum(s.get("result") == "PASS" for s in report["steps"])
    failed = sum(s.get("result") == "FAIL" for s in report["steps"])

    print("\n========================================")
    print(f"Gesamtergebnis: {report['result']}")
    print(f"Bestanden: {passed} | Fehlgeschlagen: {failed}")
    print(f"Bericht: {output}")
    print("========================================")

    if report["result"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
