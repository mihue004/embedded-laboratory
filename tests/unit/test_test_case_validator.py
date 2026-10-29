import tempfile
import unittest
from pathlib import Path

import yaml

from test_case_validator import validate_test_case, validate_test_file


def valid_case():
    return {
        "test_id": "HW-GPIO-001",
        "name": "GPIO output smoke test",
        "description": "Check GPIO output and readback.",
        "prerequisites": [
            "Compatible firmware is installed.",
            "The selected GPIO is not connected to another output.",
        ],
        "acceptance_criteria": [
            "GPIO readback matches the requested output level."
        ],
        "steps": [
            {"action": "gpio.write", "pin_number": 0, "value": "LOW"},
            {"action": "gpio.read", "pin_number": 0, "expect_value": 0},
            {"action": "gpio.write", "pin_number": 0, "value": "HIGH"},
            {"action": "gpio.read", "pin_number": 0, "expect_value": 1},
        ],
    }


class TestValidateTestCase(unittest.TestCase):
    def test_accepts_valid_case(self):
        result = validate_test_case(valid_case())
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["step_count"], 4)

    def test_missing_traceability_fields_are_warnings(self):
        case = valid_case()
        del case["test_id"]
        self.assertNotIn("requirements", case)

        result = validate_test_case(case)

        self.assertEqual(result["status"], "valid")
        self.assertTrue(any("test_id is missing" in w for w in result["warnings"]))
        self.assertTrue(any("requirements is missing" in w for w in result["warnings"]))

    def test_rejects_invalid_present_test_id(self):
        case = valid_case()
        case["test_id"] = "bad id"

        result = validate_test_case(case)

        self.assertEqual(result["status"], "error")
        self.assertTrue(any("test_id" in e for e in result["errors"]))

    def test_rejects_duplicate_requirement_links(self):
        case = valid_case()
        case["requirements"] = ["REQ-001", "REQ-001"]

        result = validate_test_case(case)

        self.assertEqual(result["status"], "error")
        self.assertTrue(any("duplicate ID" in e for e in result["errors"]))

    def test_rejects_non_mapping(self):
        result = validate_test_case(["not", "a", "mapping"])
        self.assertEqual(result["status"], "error")

    def test_rejects_missing_metadata(self):
        case = valid_case()
        del case["prerequisites"]
        del case["acceptance_criteria"]
        result = validate_test_case(case)
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("prerequisites" in e for e in result["errors"]))
        self.assertTrue(
            any("acceptance_criteria" in e for e in result["errors"])
        )

    def test_rejects_unknown_action(self):
        case = valid_case()
        case["steps"] = [{"action": "signal.measure"}]
        result = validate_test_case(case)
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("unsupported action" in e for e in result["errors"]))

    def test_accepts_serial_ready_and_status_actions(self):
        case = valid_case()
        case["steps"] = [
            {"action": "serial.ready"},
            {"action": "serial.status", "expect_active": 0},
        ]
        result = validate_test_case(case)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["step_count"], 2)

    def test_rejects_boolean_serial_status_expectation(self):
        case = valid_case()
        case["steps"] = [
            {"action": "serial.status", "expect_active": True}
        ]
        result = validate_test_case(case)
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("expect_active" in e for e in result["errors"]))

    def test_rejects_unsupported_gpio(self):
        case = valid_case()
        case["steps"] = [
            {"action": "gpio.write", "pin_number": 23, "value": "HIGH"}
        ]
        result = validate_test_case(case)
        self.assertTrue(any("pin_number" in e for e in result["errors"]))

    def test_rejects_boolean_as_gpio_pin_or_value(self):
        case = valid_case()
        case["steps"] = [
            {"action": "gpio.write", "pin_number": True, "value": True}
        ]
        result = validate_test_case(case)
        self.assertEqual(result["status"], "error")

    def test_rejects_missing_action_fields(self):
        case = valid_case()
        case["steps"] = [{"action": "gpio.read", "pin_number": 0}]
        result = validate_test_case(case)
        self.assertTrue(any("missing fields" in e for e in result["errors"]))

    def test_rejects_invalid_signal_parameters(self):
        case = valid_case()
        case["steps"] = [
            {
                "action": "signal.square",
                "pin_number": 15,
                "frequency_hz": 0,
                "duty_percent": 100,
            }
        ]
        result = validate_test_case(case)
        self.assertTrue(any("frequency_hz" in e for e in result["errors"]))
        self.assertTrue(any("duty_percent" in e for e in result["errors"]))

    def test_rejects_unknown_step_fields(self):
        case = valid_case()
        case["steps"] = [
            {
                "action": "gpio.write",
                "pin_number": 0,
                "value": "HIGH",
                "shell_command": "not allowed",
            }
        ]
        result = validate_test_case(case)
        self.assertTrue(any("unknown fields" in e for e in result["errors"]))

    def test_loads_and_validates_yaml_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.yaml"
            path.write_text(
                yaml.safe_dump(valid_case(), sort_keys=False),
                encoding="utf-8",
            )
            result = validate_test_file(path)
            self.assertEqual(result["status"], "valid")

    def test_reports_invalid_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.yaml"
            path.write_text("steps: [\n", encoding="utf-8")
            result = validate_test_file(path)
            self.assertEqual(result["status"], "error")
            self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
