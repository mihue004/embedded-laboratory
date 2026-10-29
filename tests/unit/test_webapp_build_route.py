import sys
import tempfile
import unittest
import hashlib
from pathlib import Path
from unittest.mock import patch

from flask import Flask

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host" / "webapp"))
import app as webapp


class TestWebBuildRoute(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.projects_root = Path(self.temp_dir.name)
        self.project = self.projects_root / "test-project"
        self.project.mkdir()
        # Ein reproduzierbarer Projektzustand für die Freigabetests.
        (self.project / "main.c").write_text(
            "int main(void) { return 0; }\n",
            encoding="utf-8",
        )
        webapp.app.config.update(TESTING=True)
        self.client = webapp.app.test_client()

        with self.client.session_transaction() as session:
            session["csrf_token"] = "test-token"

        self.valid_inspection = {
            "name": "test-project",
            "id": "test-project",
            "description": "",
            "has_contract": True,
            "errors": [],
            "requirements": None,
            "tests": [],
        }
        self.valid_plan = {
            "status": "ready_for_review",
            "errors": [],
            "warnings": [],
            "checks": {
                "requirements": {
                    "requirements": [],
                },
            },
            "steps": [],
        }
        self.patches = [
            patch.object(webapp, "PROJECTS_ROOT", self.projects_root),
            patch.object(webapp, "inspect_project",
                         return_value=self.valid_inspection.copy()),
            patch.object(webapp, "list_projects", return_value=[]),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def post_build(self, **extra):
        fingerprint = webapp.project_fingerprint(self.project)
        token = webapp.build_approval_token(
            "test-project", fingerprint
        )

        data = {
            "csrf_token": "test-token",
            "project": "test-project",
            "fingerprint": fingerprint,
            "approval_token": token,
        }
        data.update(extra)
        return self.client.post("/projects/build", data=data)

    def test_missing_explicit_approval_never_calls_executor(self):
        with patch.object(webapp, "execute_build") as execute:
            response = self.post_build()

        self.assertEqual(response.status_code, 400)
        execute.assert_not_called()

    def test_analysis_displays_plan_and_approval_fields(self):
        with patch.object(
            webapp, "plan_project", return_value=self.valid_plan
        ):
            response = self.client.post(
                "/projects/analyze",
                data={
                    "csrf_token": "test-token",
                    "project": "test-project",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ready_for_review", response.data)
        self.assertIn(b'name="fingerprint"', response.data)
        self.assertIn(b'name="approval_token"', response.data)
        self.assertIn(b"Build jetzt ausf\xc3\xbchren", response.data)

    def test_analysis_displays_traceability_warnings_and_details(self):
        plan = {
            **self.valid_plan,
            "warnings": ["Requirement REQ-001 has no resolvable hardware test."],
            "checks": {
                "requirements": {"requirements": []},
                "traceability": {
                    "status": "warnings",
                    "warnings": [
                        "Requirement REQ-001 has no resolvable hardware test."
                    ],
                    "errors": [],
                    "requirement_count": 1,
                    "test_case_count": 0,
                    "covered_requirements": [],
                    "uncovered_requirements": ["REQ-001"],
                    "unresolved_test_references": [{
                        "requirement_id": "REQ-001",
                        "test_id": "HW-MISSING-001",
                    }],
                    "unknown_requirement_references": [],
                },
            },
        }

        with patch.object(webapp, "plan_project", return_value=plan):
            response = self.client.post(
                "/projects/analyze",
                data={
                    "csrf_token": "test-token",
                    "project": "test-project",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Traceability", response.data)
        self.assertIn(b"Nicht abgedeckte Anforderungen", response.data)
        self.assertIn(b"REQ-001", response.data)
        self.assertIn(b"HW-MISSING-001", response.data)
        self.assertIn(b"has no resolvable hardware test", response.data)
        self.assertIn(b"Build jetzt ausf", response.data)

    def test_changed_project_rejects_stale_approval(self):
        fingerprint = webapp.project_fingerprint(self.project)
        token = webapp.build_approval_token(
            "test-project", fingerprint
        )

        # Änderung nach der ursprünglichen Freigabe.
        (self.project / "main.c").write_text(
            "int main(void) { return 1; }\n",
            encoding="utf-8",
        )

        with patch.object(webapp, "execute_build") as execute:
            response = self.post_build(
                confirm_build="yes",
                fingerprint=fingerprint,
                approval_token=token,
            )

        self.assertEqual(response.status_code, 409)
        execute.assert_not_called()

    def test_invalid_approval_token_never_calls_executor(self):
        with patch.object(webapp, "execute_build") as execute:
            response = self.post_build(
                confirm_build="yes",
                approval_token="0" * 64,
            )

        self.assertEqual(response.status_code, 400)
        execute.assert_not_called()

    def test_tampered_fingerprint_never_calls_executor(self):
        with patch.object(webapp, "execute_build") as execute:
            response = self.post_build(
                confirm_build="yes",
                fingerprint="0" * 64,
            )

        self.assertIn(response.status_code, (400, 409))
        execute.assert_not_called()

    def test_project_contract_change_rejects_stale_approval(self):
        fingerprint = webapp.project_fingerprint(self.project)
        token = webapp.build_approval_token("test-project", fingerprint)

        contract = self.project / "project.yaml"
        contract.write_text("changed: true\\n", encoding="utf-8")

        with patch.object(webapp, "execute_build") as execute:
            response = self.post_build(
                confirm_build="yes",
                fingerprint=fingerprint,
                approval_token=token,
            )

        self.assertEqual(response.status_code, 409)
        execute.assert_not_called()

    def test_non_yes_confirmation_never_calls_executor(self):
        for confirmation in ("no", "true", "ja", "1", ""):
            with self.subTest(confirmation=confirmation):
                with patch.object(webapp, "execute_build") as execute:
                    response = self.post_build(confirm_build=confirmation)

                self.assertEqual(response.status_code, 400)
                execute.assert_not_called()

    def test_invalid_plan_blocks_execution(self):
        invalid_plan = {
            **self.valid_plan,
            "status": "error",
            "errors": ["Projektvertrag ungültig"],
        }
        with (
            patch.object(webapp, "plan_project", return_value=invalid_plan),
            patch.object(webapp, "execute_build") as execute,
        ):
            response = self.post_build(confirm_build="yes")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Build blockiert", response.data)
        execute.assert_not_called()

    def test_approved_valid_plan_calls_executor_for_selected_project(self):
        build_result = {
            "status": "passed",
            "execution_performed": True,
            "flash_performed": False,
            "tests_executed": False,
            "commands": [],
            "errors": [],
            "report_path": None,
        }
        with (
            patch.object(
                webapp, "plan_project", return_value=self.valid_plan
            ),
            patch.object(webapp.threading, "Thread") as thread,
        ):
            response = self.post_build(confirm_build="yes")

        self.assertEqual(response.status_code, 200)
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertIn(b"Build-Ergebnis", response.data)


    def test_build_logs_returns_events_and_status(self):
        job_id = "test-job"
        owner = "test-session"
        webapp.BUILD_JOBS[job_id] = {
            "owner": owner,
            "events": [{"stream": "stdout", "line": "Build läuft\n"}],
            "finished": True,
            "result": {"status": "passed"},
            "error": None,
        }
        try:
            with self.client.session_transaction() as sess:
                sess["build_session_id"] = owner

            response = self.client.get(
                f"/projects/build/{job_id}/logs"
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data["events"][0]["line"], "Build läuft\n")
            self.assertTrue(data["finished"])
            self.assertEqual(data["result"]["status"], "passed")

            with webapp.app.test_client() as other_client:
                other_response = other_client.get(
                    f"/projects/build/{job_id}/logs"
                )
            self.assertEqual(other_response.status_code, 404)
        finally:
            webapp.BUILD_JOBS.pop(job_id, None)


    def test_build_job_reports_unexpected_exception(self):
        job_id = "test-error-job"
        owner = "test-error-session"
        webapp.BUILD_JOBS[job_id] = {
            "owner": owner,
            "events": [],
            "finished": False,
            "result": None,
            "error": None,
        }

        try:
            with patch.object(
                webapp, "execute_build",
                side_effect=RuntimeError("simulierter Build-Fehler"),
            ):
                webapp.run_build_job(job_id, self.project)

            with self.client.session_transaction() as sess:
                sess["build_session_id"] = owner

            response = self.client.get(
                f"/projects/build/{job_id}/logs"
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data["finished"])
            self.assertIsNone(data["result"])
            self.assertEqual(
                data["error"], "simulierter Build-Fehler"
            )
        finally:
            webapp.BUILD_JOBS.pop(job_id, None)


if __name__ == "__main__":
    unittest.main()
