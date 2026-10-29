"""Static validation of Embedded Lab YAML test cases.

This module must never access serial ports or execute hardware commands.
"""

import re
from pathlib import Path

import yaml


VALID_GPIO_PINS = set(range(0, 23)) | {26, 27, 28}
SUPPORTED_ACTIONS = {
    "gpio.write",
    "gpio.read",
    "signal.square",
    "signal.stop",
    "serial.ready",
    "serial.status",
    "wait",
}
TEST_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{2,63}$")

TOP_LEVEL_KEYS = {
    "test_id",
    "name",
    "description",
    "requirements",
    "prerequisites",
    "acceptance_criteria",
    "steps",
}

ACTION_KEYS = {
    "gpio.write": {"action", "pin_number", "value"},
    "gpio.read": {"action", "pin_number", "expect_value"},
    "signal.square": {
        "action", "pin_number", "frequency_hz", "duty_percent"
    },
    "signal.stop": {"action"},
    "serial.ready": {"action"},
    "serial.status": {"action", "expect_active"},
    "wait": {"action", "duration_ms"},
}


def _is_integer(value):
    """True for integers, but not booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate_test_case(document):
    """Return a structured validation result without executing anything."""
    errors = []
    warnings = []

    if not isinstance(document, dict):
        return {
            "status": "error",
            "errors": ["Test case must be a YAML mapping."],
            "warnings": [],
            "step_count": 0,
        }

    unknown_keys = set(document) - TOP_LEVEL_KEYS
    if unknown_keys:
        errors.append(
            "Unknown top-level fields: " + ", ".join(sorted(unknown_keys))
        )

    test_id = document.get("test_id")
    if test_id is None:
        warnings.append(
            "test_id is missing; assign a unique ID to enable traceability."
        )
    elif not isinstance(test_id, str) or not TEST_ID_PATTERN.fullmatch(test_id):
        errors.append(
            "test_id must contain 3-64 characters: uppercase letters, "
            "digits, underscores or hyphens; it must start with a letter."
        )

    for field in ("name", "description"):
        value = document.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string.")

    requirements = document.get("requirements")
    if requirements is None:
        warnings.append(
            "requirements is missing; link this test case to requirement IDs."
        )
    elif not isinstance(requirements, list):
        errors.append("requirements must be a list.")
    else:
        seen_requirements = set()
        for index, requirement in enumerate(requirements, start=1):
            if not isinstance(requirement, str) or not requirement.strip():
                errors.append(
                    f"requirements[{index}] must be a non-empty string."
                )
            elif requirement in seen_requirements:
                errors.append(
                    f"requirements contains duplicate ID {requirement!r}."
                )
            else:
                seen_requirements.add(requirement)
        if not requirements:
            warnings.append(
                "requirements is empty; this test case has no requirement links."
            )

    for field in ("prerequisites", "acceptance_criteria"):
        value = document.get(field)
        if not isinstance(value, list) or not value:
            errors.append(f"{field} must be a non-empty list.")
            continue

        for index, item in enumerate(value, start=1):
            if not isinstance(item, str) or not item.strip():
                errors.append(
                    f"{field}[{index}] must be a non-empty string."
                )

    steps = document.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list.")
        steps = []

    for index, step in enumerate(steps, start=1):
        prefix = f"steps[{index}]"

        if not isinstance(step, dict):
            errors.append(f"{prefix} must be a mapping.")
            continue

        action = step.get("action")
        if not isinstance(action, str) or action not in SUPPORTED_ACTIONS:
            errors.append(
                f"{prefix}: unsupported action {action!r}. "
                f"Supported actions: {', '.join(sorted(SUPPORTED_ACTIONS))}."
            )
            continue

        unknown = set(step) - ACTION_KEYS[action]
        missing = ACTION_KEYS[action] - set(step)

        if unknown:
            errors.append(
                f"{prefix} ({action}): unknown fields: "
                + ", ".join(sorted(unknown))
            )
        if missing:
            errors.append(
                f"{prefix} ({action}): missing fields: "
                + ", ".join(sorted(missing))
            )

        if action in {"gpio.write", "gpio.read", "signal.square"}:
            pin = step.get("pin_number")
            if not _is_integer(pin) or pin not in VALID_GPIO_PINS:
                errors.append(
                    f"{prefix}: pin_number must be a supported GPIO "
                    "(0-22 or 26-28)."
                )

        if action == "gpio.write":
            value = step.get("value")
            if value not in ("LOW", "HIGH", 0, 1) or isinstance(value, bool):
                errors.append(
                    f"{prefix}: value must be LOW, HIGH, 0 or 1."
                )

        if action == "gpio.read":
            expected = step.get("expect_value")
            if not _is_integer(expected) or expected not in (0, 1):
                errors.append(
                    f"{prefix}: expect_value must be integer 0 or 1."
                )

        if action == "signal.square":
            frequency = step.get("frequency_hz")
            duty = step.get("duty_percent")

            if (
                not _is_integer(frequency)
                or not 1 <= frequency <= 10000
            ):
                errors.append(
                    f"{prefix}: frequency_hz must be an integer "
                    "between 1 and 10000."
                )

            if not _is_integer(duty) or not 1 <= duty <= 99:
                errors.append(
                    f"{prefix}: duty_percent must be an integer "
                    "between 1 and 99."
                )

        if action == "serial.status":
            expected_active = step.get("expect_active")
            if (
                not _is_integer(expected_active)
                or expected_active not in (0, 1)
            ):
                errors.append(
                    f"{prefix}: expect_active must be integer 0 or 1."
                )

        if action == "wait":
            duration = step.get("duration_ms")
            if not _is_integer(duration) or not 0 <= duration <= 60000:
                errors.append(
                    f"{prefix}: duration_ms must be an integer "
                    "between 0 and 60000."
                )

    return {
        "status": "valid" if not errors else "error",
        "errors": errors,
        "warnings": warnings,
        "step_count": len(steps),
    }


def validate_test_file(path):
    """Load and statically validate a YAML test file."""
    test_path = Path(path)

    try:
        with test_path.open(encoding="utf-8") as stream:
            document = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        return {
            "status": "error",
            "errors": [f"Cannot load test file: {exc}"],
            "warnings": [],
            "step_count": 0,
        }

    return validate_test_case(document)



def inspect_test_case_directory(directory):
    """Validate all YAML test cases in a directory without executing them."""
    directory = Path(directory)
    result = {
        "path": str(directory),
        "status": "no_test_cases",
        "count": 0,
        "files": [],
        "errors": [],
        "warnings": [],
    }

    if not directory.is_dir():
        result["status"] = "missing_directory"
        result["warnings"].append(
            f"Hardware test directory does not exist: {directory}"
        )
        return result

    paths = sorted(
        set(directory.rglob("*.yaml")) | set(directory.rglob("*.yml"))
    )

    for path in paths:
        validation = validate_test_file(path)
        try:
            with path.open(encoding="utf-8") as stream:
                document = yaml.safe_load(stream)
        except (OSError, yaml.YAMLError):
            document = {}

        if not isinstance(document, dict):
            document = {}

        entry = {
            "path": str(path.relative_to(directory)),
            "status": validation["status"],
            "step_count": validation["step_count"],
            "test_id": document.get("test_id"),
            "requirements": document.get("requirements"),
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        }
        result["files"].append(entry)

        for error in validation["errors"]:
            result["errors"].append(f"{entry['path']}: {error}")
        for warning in validation["warnings"]:
            result["warnings"].append(f"{entry['path']}: {warning}")

    result["count"] = len(result["files"])

    seen_test_ids = {}
    for entry in result["files"]:
        test_id = entry["test_id"]
        if not isinstance(test_id, str) or not TEST_ID_PATTERN.fullmatch(test_id):
            continue
        if test_id in seen_test_ids:
            message = (
                f"Duplicate test_id {test_id!r} in "
                f"{seen_test_ids[test_id]!r} and {entry['path']!r}."
            )
            result["errors"].append(message)
        else:
            seen_test_ids[test_id] = entry["path"]

    if result["errors"]:
        result["status"] = "error"
    elif result["count"]:
        result["status"] = "valid"

    if result["status"] == "no_test_cases":
        result["warnings"].append(
            "No YAML hardware test cases were found."
        )

    return result
