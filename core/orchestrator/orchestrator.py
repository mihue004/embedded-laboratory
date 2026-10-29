#!/usr/bin/env python3
"""Plan and validate an Embedded Lab project without executing it."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core" / "project_manager"))

from validate_project import validate_project  # noqa: E402
from test_case_validator import inspect_test_case_directory  # noqa: E402


REQUIREMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def resolve_inside_project(project_root: Path, relative_path: str) -> Path:
    """Resolve a contract path and reject paths escaping the project root."""
    root = project_root.resolve()
    candidate = (root / relative_path).resolve()

    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Path escapes project directory: {relative_path}")

    return candidate


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def inspect_requirements(path: Path) -> dict:
    """Check the basic structure of the requirements document."""
    result = {
        "path": str(path),
        "status": "error",
        "count": 0,
        "errors": [],
        "requirements": [],
    }

    if not path.is_file():
        result["errors"].append("Requirements file does not exist.")
        return result

    try:
        document = load_yaml(path)
    except (OSError, yaml.YAMLError) as exc:
        result["errors"].append(f"Cannot read requirements YAML: {exc}")
        return result

    if not isinstance(document, dict):
        result["errors"].append("Requirements document must be a YAML mapping.")
        return result

    if document.get("requirements_version") != "1.0":
        result["errors"].append(
            "requirements_version must be the string '1.0'."
        )

    requirements = document.get("requirements")
    if not isinstance(requirements, list):
        result["errors"].append("'requirements' must be a list.")
        return result

    seen_ids = set()

    for index, requirement in enumerate(requirements):
        prefix = f"requirements[{index}]"

        if not isinstance(requirement, dict):
            result["errors"].append(f"{prefix} must be a mapping.")
            continue

        requirement_id = requirement.get("id")
        description = requirement.get("description")
        verification = requirement.get("verification", [])

        if not isinstance(requirement_id, str) or not REQUIREMENT_ID.fullmatch(
            requirement_id
        ):
            result["errors"].append(f"{prefix}.id is missing or invalid.")
        elif requirement_id in seen_ids:
            result["errors"].append(
                f"{prefix}.id duplicates {requirement_id!r}."
            )
        else:
            seen_ids.add(requirement_id)

        if not isinstance(description, str) or not description.strip():
            result["errors"].append(
                f"{prefix}.description must be a non-empty string."
            )

        if not isinstance(verification, list):
            result["errors"].append(
                f"{prefix}.verification must be a list."
            )
        else:
            seen_hardware_refs = set()
            for method_index, method in enumerate(verification):
                method_prefix = f"{prefix}.verification[{method_index}]"

                if not isinstance(method, dict) or len(method) != 1:
                    result["errors"].append(
                        f"{method_prefix} must contain exactly one "
                        "verification method."
                    )
                    continue

                method_name, reference = next(iter(method.items()))

                if (
                    not isinstance(method_name, str)
                    or not re.fullmatch(r"[a-z][a-z0-9_]*", method_name)
                ):
                    result["errors"].append(
                        f"{method_prefix} has an invalid method name."
                    )

                if not isinstance(reference, str) or not reference.strip():
                    result["errors"].append(
                        f"{method_prefix} reference must be a "
                        "non-empty string."
                    )
                    continue

                if method_name == "hardware_test":
                    if not re.fullmatch(r"[A-Z][A-Z0-9_-]{2,63}", reference):
                        result["errors"].append(
                            f"{method_prefix}.hardware_test has an "
                            "invalid test ID."
                        )
                    elif reference in seen_hardware_refs:
                        result["errors"].append(
                            f"{method_prefix} duplicates hardware test "
                            f"reference {reference!r}."
                        )
                    else:
                        seen_hardware_refs.add(reference)

        result["requirements"].append(
            {
                "id": requirement_id,
                "description": description,
                "verification": verification,
            }
        )

    result["count"] = len(result["requirements"])
    result["status"] = "valid" if not result["errors"] else "error"
    return result


def inspect_traceability(requirements_result: dict, test_cases: dict) -> dict:
    """Check requirement-to-test links in both directions."""
    requirements = requirements_result.get("requirements", [])
    cases = test_cases.get("files", [])

    result = {
        "status": "valid",
        "errors": [],
        "warnings": [],
        "requirement_count": requirements_result.get("count", 0),
        "test_case_count": test_cases.get("count", 0),
        "covered_requirements": [],
        "uncovered_requirements": [],
        "unresolved_test_references": [],
        "unknown_requirement_references": [],
    }

    requirement_ids = {
        item["id"]
        for item in requirements
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    test_ids = {
        item["test_id"]
        for item in cases
        if isinstance(item, dict) and isinstance(item.get("test_id"), str)
    }

    requirement_test_refs = {}
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue

        requirement_id = requirement.get("id")
        if not isinstance(requirement_id, str):
            continue

        refs = set()
        verification = requirement.get("verification", [])
        if isinstance(verification, list):
            for method in verification:
                if isinstance(method, dict) and "hardware_test" in method:
                    test_id = method["hardware_test"]
                    if isinstance(test_id, str) and test_id.strip():
                        refs.add(test_id)

        requirement_test_refs[requirement_id] = refs

    test_case_requirements = {}
    for case in cases:
        if not isinstance(case, dict):
            continue

        test_id = case.get("test_id")
        if not isinstance(test_id, str):
            continue

        linked = case.get("requirements")
        if linked is None:
            # The test-case validator already reports missing links as a warning.
            # Keep traceability consistent with that policy.
            linked = []
        elif not isinstance(linked, list):
            result["errors"].append(
                f"Test {test_id} has an invalid requirements list."
            )
            linked = []

        linked_ids = set()
        for requirement_id in linked:
            if not isinstance(requirement_id, str) or not requirement_id.strip():
                result["errors"].append(
                    f"Test {test_id} contains an invalid requirement reference."
                )
                continue

            if requirement_id not in requirement_ids:
                result["unknown_requirement_references"].append({
                    "test_id": test_id,
                    "requirement_id": requirement_id,
                })
                result["errors"].append(
                    f"Test {test_id} references unknown requirement "
                    f"{requirement_id}."
                )
                continue

            if requirement_id in linked_ids:
                result["errors"].append(
                    f"Test {test_id} contains duplicate requirement "
                    f"reference {requirement_id}."
                )
                continue

            linked_ids.add(requirement_id)

            if test_id not in requirement_test_refs.get(requirement_id, set()):
                result["errors"].append(
                    f"Test {test_id} links requirement {requirement_id}, "
                    "but that requirement does not reference this test."
                )

        test_case_requirements[test_id] = linked_ids

    referenced_test_ids = set()

    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue

        requirement_id = requirement.get("id")
        if not isinstance(requirement_id, str):
            continue

        refs = requirement_test_refs.get(requirement_id, set())
        resolved_and_linked = False

        for test_id in sorted(refs):
            referenced_test_ids.add(test_id)

            if test_id not in test_ids:
                result["unresolved_test_references"].append({
                    "requirement_id": requirement_id,
                    "test_id": test_id,
                })
                result["warnings"].append(
                    f"Requirement {requirement_id} references hardware test "
                    f"{test_id}, but no matching test case was found."
                )
                continue

            if requirement_id not in test_case_requirements.get(test_id, set()):
                result["errors"].append(
                    f"Requirement {requirement_id} references test {test_id}, "
                    "but that test does not list the requirement."
                )
                continue

            resolved_and_linked = True

        if resolved_and_linked:
            result["covered_requirements"].append(requirement_id)
        else:
            result["uncovered_requirements"].append(requirement_id)
            if not refs:
                result["warnings"].append(
                    f"Requirement {requirement_id} has no hardware test "
                    "verification reference."
                )
            elif not any(test_id in test_ids for test_id in refs):
                result["warnings"].append(
                    f"Requirement {requirement_id} has no resolvable "
                    "hardware test."
                )

    for test_id in sorted(test_ids - referenced_test_ids):
        result["warnings"].append(
            f"Test case {test_id} is not referenced by any requirement's "
            "hardware_test verification."
        )

    result["errors"] = list(dict.fromkeys(result["errors"]))
    result["warnings"] = list(dict.fromkeys(result["warnings"]))

    if result["errors"]:
        result["status"] = "error"
    elif result["warnings"]:
        result["status"] = "warnings"

    return result


def plan_project(project_dir: Path) -> dict:
    """Validate a project and create a plan; never execute project commands."""
    project_root = project_dir.expanduser().resolve()
    config_path = project_root / "project.yaml"

    plan = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_dir": str(project_root),
        "mode": "plan_only",
        "execution_performed": False,
        "flash_performed": False,
        "status": "error",
        "checks": {},
        "steps": [],
        "errors": [],
        "warnings": [],
    }

    if not project_root.is_dir():
        plan["errors"].append(f"Project directory does not exist: {project_root}")
        return plan

    if not config_path.is_file():
        plan["errors"].append(f"Missing project contract: {config_path}")
        return plan

    schema_path = ROOT / "schemas" / "project.schema.yaml"
    schema_errors = validate_project(config_path, schema_path)
    plan["checks"]["project_contract"] = {
        "status": "valid" if not schema_errors else "error",
        "errors": schema_errors,
    }

    if schema_errors:
        plan["errors"].extend(
            f"Project contract: {error}" for error in schema_errors
        )
        return plan

    try:
        config = load_yaml(config_path)
    except (OSError, yaml.YAMLError) as exc:
        plan["errors"].append(f"Cannot read project contract: {exc}")
        return plan

    resolved_paths = {}
    for key, relative_path in (
        ("source_dir", config["build"]["source_dir"]),
        ("build_dir", config["build"]["build_dir"]),
        ("requirements_file", config["requirements"]["file"]),
        ("artifacts_dir", config["artifacts"]["directory"]),
        ("reports_dir", config["artifacts"]["reports_directory"]),
    ):
        try:
            resolved_paths[key] = resolve_inside_project(
                project_root, relative_path
            )
        except (ValueError, OSError) as exc:
            plan["errors"].append(f"Invalid {key}: {exc}")

    if plan["errors"]:
        return plan

    source_dir = resolved_paths["source_dir"]
    build_dir = resolved_paths["build_dir"]
    requirements_file = resolved_paths["requirements_file"]

    source_exists = source_dir.is_dir()
    plan["checks"]["build_source"] = {
        "status": "present" if source_exists else "error",
        "path": str(source_dir),
    }
    if not source_exists:
        plan["errors"].append(f"Build source directory does not exist: {source_dir}")

    build_system = config["build"]["system"]
    build_file = {
        "cmake": "CMakeLists.txt",
        "make": "Makefile",
        "platformio": "platformio.ini",
    }[build_system]
    build_file_path = source_dir / build_file
    build_config_exists = build_file_path.is_file()

    plan["checks"]["build_configuration"] = {
        "system": build_system,
        "status": "present" if build_config_exists else "error",
        "path": str(build_file_path),
    }
    if not build_config_exists:
        plan["errors"].append(
            f"Missing build configuration for {build_system}: {build_file_path}"
        )

    requirements_result = inspect_requirements(requirements_file)
    plan["checks"]["requirements"] = requirements_result
    if requirements_result["errors"]:
        plan["errors"].extend(
            f"Requirements: {error}"
            for error in requirements_result["errors"]
        )

    test_dirs = {}
    for key in ("unit_test_dir", "integration_test_dir", "hardware_test_dir"):
        relative_path = config["testing"].get(key)
        if relative_path is None:
            continue

        try:
            path = resolve_inside_project(project_root, relative_path)
        except (ValueError, OSError) as exc:
            plan["errors"].append(f"Invalid {key}: {exc}")
            continue

        exists = path.is_dir()
        test_dirs[key] = {
            "path": str(path),
            "status": "present" if exists else "missing",
        }
        if not exists:
            plan["warnings"].append(
                f"Configured test directory does not exist: {relative_path}"
            )

    plan["checks"]["test_directories"] = test_dirs

    hardware_test_info = test_dirs.get("hardware_test_dir")
    if hardware_test_info is not None:
        test_case_result = inspect_test_case_directory(
            Path(hardware_test_info["path"])
        )
        plan["checks"]["hardware_test_cases"] = test_case_result

        for error in test_case_result["errors"]:
            plan["errors"].append(f"Hardware test cases: {error}")

        plan["warnings"].extend(test_case_result["warnings"])

        traceability_result = inspect_traceability(
            requirements_result, test_case_result
        )
        plan["checks"]["traceability"] = traceability_result
        plan["warnings"].extend(traceability_result["warnings"])
        for error in traceability_result["errors"]:
            plan["errors"].append(f"Traceability: {error}")
    else:
        plan["checks"]["traceability"] = {
            "status": "not_configured",
            "errors": [],
            "warnings": ["Hardware test directory is not configured."],
            "requirement_count": requirements_result.get("count", 0),
            "test_case_count": 0,
            "covered_requirements": [],
            "uncovered_requirements": [],
            "unresolved_test_references": [],
            "unknown_requirement_references": [],
        }

    plan["checks"]["build_directory"] = {
        "path": str(build_dir),
        "status": "already_exists" if build_dir.exists() else "not_created",
    }

    plan["steps"] = [
        {
            "id": "validate_contract",
            "description": "Validate project.yaml against the project schema.",
            "status": "passed",
        },
        {
            "id": "inspect_requirements",
            "description": "Check requirement IDs, descriptions and verification entries.",
            "status": requirements_result["status"],
        },
        {
            "id": "validate_test_cases",
            "description": (
                "Discover and statically validate YAML hardware test cases. "
                "No hardware commands are executed."
            ),
            "status": (
                plan["checks"]["hardware_test_cases"]["status"]
                if "hardware_test_cases" in plan["checks"]
                else "not_configured"
            ),
        },
        {
            "id": "check_traceability",
            "description": (
                "Compare requirement verification references with test case "
                "IDs and requirement links. Static checks only."
            ),
            "status": plan["checks"]["traceability"]["status"],
        },
        {
            "id": "configure_build",
            "description": (
                f"Configure {build_system} build in {build_dir}. "
                "Not executed in plan-only mode."
            ),
            "status": "planned",
            "requires_approval": True,
        },
        {
            "id": "run_software_tests",
            "description": "Discover and execute applicable software tests.",
            "status": "planned",
            "requires_approval": True,
        },
        {
            "id": "run_hardware_tests",
            "description": "Run approved hardware tests on configured devices.",
            "status": "not_started",
            "requires_approval": True,
        },
        {
            "id": "flash_firmware",
            "description": "Firmware flashing is never part of automatic planning.",
            "status": "blocked",
            "requires_explicit_approval": True,
        },
    ]

    plan["status"] = "ready_for_review" if not plan["errors"] else "error"
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an Embedded Lab project and print an execution plan."
    )
    parser.add_argument("project_dir", type=Path, help="Directory containing project.yaml")
    args = parser.parse_args()

    plan = plan_project(args.project_dir)
    print(json.dumps(plan, indent=2, ensure_ascii=False))

    return 0 if plan["status"] == "ready_for_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
