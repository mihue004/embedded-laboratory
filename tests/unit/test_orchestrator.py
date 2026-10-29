import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from orchestrator import (
    inspect_requirements,
    inspect_traceability,
    plan_project,
    resolve_inside_project,
)


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "pico-sdk"


class TestResolveInsideProject(unittest.TestCase):
    def test_accepts_path_inside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()

            result = resolve_inside_project(root, "src")

            self.assertEqual(result, (root / "src").resolve())

    def test_rejects_parent_directory_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaises(ValueError):
                resolve_inside_project(root, "../outside")

    def test_rejects_absolute_path_outside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with tempfile.TemporaryDirectory() as outside:
                with self.assertRaises(ValueError):
                    resolve_inside_project(root, outside)


class TestInspectRequirements(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.requirements_file = self.root / "requirements.yaml"

    def write_requirements(self, document):
        self.requirements_file.write_text(
            yaml.safe_dump(document, sort_keys=False),
            encoding="utf-8",
        )

    def test_accepts_valid_requirements(self):
        self.write_requirements({
            "requirements_version": "1.0",
            "requirements": [
                {
                    "id": "REQ-001",
                    "description": "Initialize serial output.",
                    "verification": [{"hardware_test": "HW-001"}],
                }
            ],
        })

        result = inspect_requirements(self.requirements_file)

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["requirements"][0]["id"], "REQ-001")
        self.assertEqual(result["errors"], [])

    def test_reports_missing_file(self):
        result = inspect_requirements(self.root / "missing.yaml")

        self.assertEqual(result["status"], "error")
        self.assertTrue(result["errors"])

    def test_reports_invalid_yaml(self):
        self.requirements_file.write_text(
            "requirements: [\n",
            encoding="utf-8",
        )

        result = inspect_requirements(self.requirements_file)

        self.assertEqual(result["status"], "error")
        self.assertTrue(result["errors"])

    def test_rejects_duplicate_requirement_ids(self):
        self.write_requirements({
            "requirements_version": "1.0",
            "requirements": [
                {"id": "REQ-001", "description": "First requirement."},
                {"id": "REQ-001", "description": "Second requirement."},
            ],
        })

        result = inspect_requirements(self.requirements_file)

        self.assertEqual(result["status"], "error")
        self.assertTrue(
            any("duplicates" in error for error in result["errors"])
        )

    def test_rejects_empty_description(self):
        self.write_requirements({
            "requirements_version": "1.0",
            "requirements": [
                {"id": "REQ-001", "description": "   "},
            ],
        })

        result = inspect_requirements(self.requirements_file)

        self.assertEqual(result["status"], "error")
        self.assertTrue(
            any("description" in error for error in result["errors"])
        )

    def test_rejects_verification_with_multiple_methods(self):
        self.write_requirements({
            "requirements_version": "1.0",
            "requirements": [
                {
                    "id": "REQ-001",
                    "description": "Check the output.",
                    "verification": [
                        {
                            "hardware_test": "HW-001",
                            "unit_test": "UT-001",
                        }
                    ],
                }
            ],
        })

        result = inspect_requirements(self.requirements_file)

        self.assertEqual(result["status"], "error")
        self.assertTrue(
            any(
                "exactly one verification method" in error
                for error in result["errors"]
            )
        )


class TestInspectTraceability(unittest.TestCase):
    def test_accepts_reciprocal_requirement_and_test_links(self):
        requirements = {
            "count": 1,
            "requirements": [{
                "id": "REQ-001",
                "verification": [{"hardware_test": "HW-001"}],
            }],
        }
        test_cases = {
            "count": 1,
            "files": [{
                "test_id": "HW-001",
                "requirements": ["REQ-001"],
            }],
            "errors": [],
        }

        result = inspect_traceability(requirements, test_cases)

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["covered_requirements"], ["REQ-001"])
        self.assertEqual(result["uncovered_requirements"], [])
        self.assertEqual(result["errors"], [])

    def test_rejects_malformed_hardware_test_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "requirements.yaml"
            path.write_text(
                yaml.safe_dump({
                    "requirements_version": "1.0",
                    "requirements": [{
                        "id": "REQ-001",
                        "description": "Check output.",
                        "verification": [{"hardware_test": "bad id"}],
                    }],
                }),
                encoding="utf-8",
            )

            result = inspect_requirements(path)

        self.assertEqual(result["status"], "error")
        self.assertTrue(
            any("invalid test ID" in error for error in result["errors"])
        )

    def test_reports_unresolved_hardware_test_reference_as_warning(self):
        requirements = {
            "count": 1,
            "requirements": [{
                "id": "REQ-001",
                "verification": [{"hardware_test": "HW-MISSING-001"}],
            }],
        }
        test_cases = {
            "count": 0,
            "files": [],
            "errors": [],
        }

        result = inspect_traceability(requirements, test_cases)

        self.assertEqual(result["status"], "warnings")
        self.assertEqual(len(result["unresolved_test_references"]), 1)
        self.assertEqual(result["uncovered_requirements"], ["REQ-001"])

    def test_reports_matching_ids_and_missing_backlink(self):
        requirements = {
            "count": 1,
            "requirements": [{
                "id": "REQ-001",
                "verification": [{"hardware_test": "HW-001"}],
            }],
        }
        test_cases = {
            "count": 1,
            "files": [{
                "test_id": "HW-001",
                "requirements": [],
            }],
            "errors": [],
        }

        result = inspect_traceability(requirements, test_cases)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["covered_requirements"], [])
        self.assertTrue(any("does not list the requirement" in e
                            for e in result["errors"]))

    def test_reports_unknown_requirement_link(self):
        requirements = {
            "count": 0,
            "requirements": [],
        }
        test_cases = {
            "count": 1,
            "files": [{
                "test_id": "HW-001",
                "requirements": ["REQ-UNKNOWN"],
            }],
            "errors": [],
        }

        result = inspect_traceability(requirements, test_cases)

        self.assertEqual(result["status"], "error")
        self.assertEqual(len(result["unknown_requirement_references"]), 1)
        self.assertTrue(any("unknown requirement" in e
                            for e in result["errors"]))


class TestPlanProject(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.project = self.root / "test-project"
        shutil.copytree(TEMPLATE, self.project)

    def test_valid_template_is_ready_for_review(self):
        plan = plan_project(self.project)

        self.assertEqual(plan["status"], "ready_for_review")
        self.assertEqual(plan["mode"], "plan_only")
        self.assertFalse(plan["execution_performed"])
        self.assertFalse(plan["flash_performed"])
        self.assertEqual(
            plan["checks"]["requirements"]["count"],
            2,
        )

    def test_plan_reports_empty_hardware_test_directory(self):
        plan = plan_project(self.project)

        result = plan["checks"]["hardware_test_cases"]
        self.assertEqual(result["status"], "no_test_cases")
        self.assertEqual(result["count"], 0)
        self.assertFalse(plan["execution_performed"])
        self.assertFalse(plan["flash_performed"])

    def test_plan_rejects_invalid_hardware_test_case(self):
        hardware_dir = self.project / "tests" / "hardware"
        hardware_dir.mkdir(parents=True, exist_ok=True)
        (hardware_dir / "invalid.yaml").write_text(
            "test_id: HW-GPIO-001\n"
            "name: Invalid test\n"
            "description: Missing required fields\n"
            "steps:\n"
            "  - action: signal.measure\n",
            encoding="utf-8",
        )

        plan = plan_project(self.project)

        self.assertEqual(plan["status"], "error")
        self.assertEqual(
            plan["checks"]["hardware_test_cases"]["status"], "error"
        )
        self.assertTrue(
            any("unsupported action" in error for error in plan["errors"])
        )
        self.assertFalse(plan["execution_performed"])
        self.assertFalse(plan["flash_performed"])

    def test_plan_accepts_valid_hardware_test_case(self):
        hardware_dir = self.project / "tests" / "hardware"
        hardware_dir.mkdir(parents=True, exist_ok=True)
        (hardware_dir / "gpio.yaml").write_text(
            "test_id: HW-GPIO-001\n"
            "name: GPIO smoke test\n"
            "description: Check GPIO readback\n"
            "prerequisites:\n"
            "  - Compatible firmware is installed\n"
            "acceptance_criteria:\n"
            "  - GPIO readback matches the written level\n"
            "steps:\n"
            "  - action: gpio.write\n"
            "    pin_number: 0\n"
            "    value: LOW\n"
            "  - action: gpio.read\n"
            "    pin_number: 0\n"
            "    expect_value: 0\n",
            encoding="utf-8",
        )

        plan = plan_project(self.project)

        self.assertEqual(plan["status"], "ready_for_review")
        result = plan["checks"]["hardware_test_cases"]
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["count"], 1)
        self.assertTrue(plan["warnings"])
        self.assertEqual(plan["errors"], [])
        self.assertEqual(
            plan["checks"]["traceability"]["status"], "warnings"
        )
        self.assertFalse(plan["execution_performed"])
        self.assertFalse(plan["flash_performed"])

    def test_plan_does_not_create_build_directory(self):
        build_dir = self.project / "build"

        self.assertFalse(build_dir.exists())

        plan = plan_project(self.project)

        self.assertFalse(build_dir.exists())
        self.assertEqual(
            plan["checks"]["build_directory"]["status"],
            "not_created",
        )

    def test_flash_step_is_blocked_and_requires_explicit_approval(self):
        plan = plan_project(self.project)

        flash_step = next(
            step for step in plan["steps"]
            if step["id"] == "flash_firmware"
        )

        self.assertEqual(flash_step["status"], "blocked")
        self.assertTrue(flash_step["requires_explicit_approval"])
        self.assertFalse(plan["flash_performed"])

    def test_missing_build_configuration_is_an_error(self):
        (self.project / "CMakeLists.txt").unlink()

        plan = plan_project(self.project)

        self.assertEqual(plan["status"], "error")
        self.assertEqual(
            plan["checks"]["build_configuration"]["status"],
            "error",
        )
        self.assertTrue(
            any("Missing build configuration" in error
                for error in plan["errors"])
        )

    def test_missing_project_contract_is_an_error(self):
        (self.project / "project.yaml").unlink()

        plan = plan_project(self.project)

        self.assertEqual(plan["status"], "error")
        self.assertTrue(
            any("Missing project contract" in error
                for error in plan["errors"])
        )

    def test_nonexistent_project_is_an_error(self):
        plan = plan_project(self.root / "does-not-exist")

        self.assertEqual(plan["status"], "error")
        self.assertFalse(plan["execution_performed"])
        self.assertFalse(plan["flash_performed"])


if __name__ == "__main__":
    unittest.main()
