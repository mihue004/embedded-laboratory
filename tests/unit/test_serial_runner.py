import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host" / "testbench"))

import runner


class FakePort:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.commands = []

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.commands.append(data.decode("ascii"))

    def flush(self):
        pass

    def readline(self):
        if not self.responses:
            return b""
        return self.responses.pop(0)


def test_wait_for_ready_accepts_exact_startup_message():
    port = FakePort(b"noise\n", b"READY,TESTBENCH,1\n")

    assert runner.wait_for_ready(port) == "READY,TESTBENCH,1"


def test_wait_for_ready_rejects_missing_startup_message():
    port = FakePort(b"BOOTING\n", b"")

    with patch.object(runner.time, "monotonic", side_effect=[0, 0, 9]):
        with pytest.raises(TimeoutError, match="Startmeldung"):
            runner.wait_for_ready(port, timeout_seconds=8)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0),
        (1, 1),
        ("LOW", 0),
        ("HIGH", 1),
        (False, 0),
        (True, 1),
    ],
)
def test_gpio_write_validates_response_and_value(value, expected):
    port = FakePort(
        f"OK,WRITE,GPIO=4,VALUE={expected}\n".encode()
    )

    result = runner.execute_step(
        port,
        {"action": "gpio.write", "pin_number": 4, "value": value},
    )

    assert result["result"] == "PASS"
    assert port.commands == [f"WRITE,4,{expected}\n"]


def test_gpio_write_rejects_wrong_response():
    port = FakePort(b"UNEXPECTED,OK\n")

    with pytest.raises(RuntimeError, match="Unerwartete Antwort"):
        runner.execute_step(
            port,
            {"action": "gpio.write", "pin_number": 4, "value": 1},
        )


def test_gpio_read_checks_pin_and_value():
    port = FakePort(b"VALUE,4,1\n")

    result = runner.execute_step(
        port,
        {
            "action": "gpio.read",
            "pin_number": 4,
            "expect_value": 1,
        },
    )

    assert result["result"] == "PASS"


def test_gpio_read_rejects_wrong_pin():
    port = FakePort(b"VALUE,5,1\n")

    with pytest.raises(RuntimeError, match="Falscher GPIO"):
        runner.execute_step(
            port,
            {
                "action": "gpio.read",
                "pin_number": 4,
                "expect_value": 1,
            },
        )


def test_gpio_read_rejects_wrong_value():
    port = FakePort(b"VALUE,4,0\n")

    with pytest.raises(AssertionError, match="erwartet 1"):
        runner.execute_step(
            port,
            {
                "action": "gpio.read",
                "pin_number": 4,
                "expect_value": 1,
            },
        )


def test_signal_square_checks_parameters():
    port = FakePort(b"OK,SIGNAL,GPIO=15,FREQ=1000,DUTY=50\n")

    result = runner.execute_step(
        port,
        {
            "action": "signal.square",
            "pin_number": 15,
            "frequency_hz": 1000,
            "duty_percent": 50,
        },
    )

    assert result["result"] == "PASS"


def test_signal_square_rejects_wrong_frequency():
    port = FakePort(b"OK,SIGNAL,GPIO=15,FREQ=500,DUTY=50\n")

    with pytest.raises(RuntimeError, match="FREQ=1000"):
        runner.execute_step(
            port,
            {
                "action": "signal.square",
                "pin_number": 15,
                "frequency_hz": 1000,
                "duty_percent": 50,
            },
        )


def test_signal_stop_requires_exact_response():
    port = FakePort(b"OK,STOPPED\n")

    assert runner.execute_step(
        port, {"action": "signal.stop"}
    )["result"] == "PASS"


def test_signal_stop_rejects_unexpected_response():
    port = FakePort(b"OK\n")

    with pytest.raises(RuntimeError, match="Unerwartete Antwort"):
        runner.execute_step(port, {"action": "signal.stop"})


def test_empty_response_is_timeout():
    port = FakePort(b"")

    with pytest.raises(TimeoutError, match="Keine Antwort"):
        runner.execute_step(
            port,
            {"action": "gpio.write", "pin_number": 4, "value": 1},
        )


def test_firmware_error_is_failure():
    port = FakePort(b"ERR,INVALID_GPIO\n")

    with pytest.raises(RuntimeError, match="INVALID_GPIO"):
        runner.execute_step(
            port,
            {"action": "gpio.write", "pin_number": 4, "value": 1},
        )


def test_serial_ready_uses_captured_startup_message():
    port = FakePort()
    port._testbench_startup_response = "READY,TESTBENCH,1"

    result = runner.execute_step(port, {"action": "serial.ready"})

    assert result["result"] == "PASS"
    assert result["response"] == "READY,TESTBENCH,1"
    assert port.commands == []


def test_serial_ready_fails_if_startup_was_not_captured():
    port = FakePort()

    with pytest.raises(RuntimeError, match="nicht zuverlässig erfasst"):
        runner.execute_step(port, {"action": "serial.ready"})


def test_serial_status_checks_inactive_state():
    port = FakePort(b"STATUS,ACTIVE=0,GPIO=0,FREQ=0,DUTY=0\n")

    result = runner.execute_step(
        port, {"action": "serial.status", "expect_active": 0}
    )

    assert result["result"] == "PASS"
    assert port.commands == ["STATUS\n"]


def test_serial_status_checks_active_state():
    port = FakePort(b"STATUS,ACTIVE=1,GPIO=15,FREQ=1000,DUTY=50\n")

    result = runner.execute_step(
        port, {"action": "serial.status", "expect_active": 1}
    )

    assert result["result"] == "PASS"


def test_serial_status_rejects_wrong_active_state():
    port = FakePort(b"STATUS,ACTIVE=0,GPIO=15,FREQ=1000,DUTY=50\n")

    with pytest.raises(AssertionError, match="STATUS ACTIVE"):
        runner.execute_step(
            port, {"action": "serial.status", "expect_active": 1}
        )


def test_serial_status_rejects_malformed_response():
    port = FakePort(b"STATUS,ACTIVE=0\\n")

    with pytest.raises(RuntimeError, match="STATUS"):
        runner.execute_step(
            port, {"action": "serial.status", "expect_active": 0}
        )
