#!/usr/bin/env python3
"""Embedded Lab local web interface."""

import os
import re
import secrets
import sys
import hashlib
import hmac
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

ROOT = Path(__file__).resolve().parents[2]
PROJECTS_ROOT = Path(
    os.environ.get("EMBEDDED_PROJECTS_ROOT", "~/embedded-projects")
).expanduser().resolve()
TEMPLATE = ROOT / "templates" / "pico-sdk"

sys.path.insert(0, str(ROOT / "core" / "project_manager"))
from project_manager import create_project, import_repository, validate_imported_project
sys.path.insert(0, str(ROOT / "core" / "orchestrator"))
from orchestrator import plan_project
from build_executor import execute_build

app = Flask(__name__)
from settings.routes import settings_bp

app.register_blueprint(settings_bp, url_prefix="/settings")
app.secret_key = os.environ.get("EMBEDDED_LAB_SESSION_SECRET") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
)

BUILD_JOBS = {}
BUILD_JOBS_LOCK = threading.Lock()

MAX_BUILD_JOBS = 20
MAX_BUILD_EVENTS = 2000
BUILD_JOB_RETENTION_SECONDS = 1800


def _cleanup_build_jobs_locked(now=None, reserve_slot=False):
    now = time.time() if now is None else now

    expired = [
        job_id
        for job_id, job in BUILD_JOBS.items()
        if job.get("finished")
        and job.get("finished_at") is not None
        and now - job["finished_at"] >= BUILD_JOB_RETENTION_SECONDS
    ]
    for job_id in expired:
        del BUILD_JOBS[job_id]

    limit = MAX_BUILD_JOBS - 1 if reserve_slot else MAX_BUILD_JOBS

    while len(BUILD_JOBS) > limit:
        finished_jobs = [
            (job.get("finished_at") or job.get("created_at") or 0, job_id)
            for job_id, job in BUILD_JOBS.items()
            if job.get("finished")
        ]
        if not finished_jobs:
            break

        _, oldest_job_id = min(finished_jobs)
        del BUILD_JOBS[oldest_job_id]


def cleanup_build_jobs(now=None):
    with BUILD_JOBS_LOCK:
        _cleanup_build_jobs_locked(now=now)


def append_build_event(job_id, event):
    with BUILD_JOBS_LOCK:
        job = BUILD_JOBS.get(job_id)
        if job is None:
            return

        job["events"].append(event)
        overflow = len(job["events"]) - MAX_BUILD_EVENTS
        if overflow > 0:
            del job["events"][:overflow]
            job["event_offset"] = job.get("event_offset", 0) + overflow


def project_fingerprint(project_dir):
    """Hash project files while excluding generated output and caches."""
    root = Path(project_dir).resolve()
    digest = hashlib.sha256()
    excluded = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "build",
        "artifacts",
    }

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)

        if any(part in excluded for part in relative.parts):
            continue

        # Never follow symlinks or include their targets.
        if path.is_symlink():
            raise ValueError(
                f"Symlinks are not allowed in the project: {relative}"
            )

        if not path.is_file():
            continue

        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")

        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)

        digest.update(b"\0")

    return digest.hexdigest()


def build_approval_token(project_name, fingerprint):
    message = f"{project_name}:{fingerprint}".encode("utf-8")
    key = str(app.secret_key).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def ensure_projects_root():
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)


def valid_project_id(project_id):
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", project_id or ""))


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        supplied = (
            request.form.get("csrf_token")
            or request.headers.get("X-CSRF-Token", "")
        )
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(400, "Ungültiges oder abgelaufenes Formular-Token.")


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token()}

def run_build_job(job_id, project_path):
    def on_event(event):
        append_build_event(job_id, event)

    try:
        result = execute_build(
            project_path,
            approved=True,
            event_callback=on_event,
        )
        with BUILD_JOBS_LOCK:
            job = BUILD_JOBS.get(job_id)
            if job is not None:
                job["result"] = result
                job["finished"] = True
                job["finished_at"] = time.time()
    except Exception as exc:
        with BUILD_JOBS_LOCK:
            job = BUILD_JOBS.get(job_id)
            if job is not None:
                job["error"] = str(exc)
                job["finished"] = True
                job["finished_at"] = time.time()

def inspect_project(path):
    config = path / "project.yaml"
    errors = validate_imported_project(path) if config.is_file() else []
    has_contract = config.is_file()
    requirements = None
    tests = []

    if has_contract and not errors:
        import yaml
        try:
            data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
            rel = data.get("requirements", {}).get("file")
            if rel:
                requirements = rel if (path / rel).is_file() else f"{rel} (fehlt)"
        except (OSError, yaml.YAMLError, AttributeError):
            pass

    for folder in ("tests", "test", "unit_tests"):
        root = path / folder
        if root.is_dir():
            try:
                for item in root.rglob("*"):
                    if item.is_file() and item.suffix.lower() in (".yaml", ".yml", ".py", ".c", ".cpp"):
                        if len(tests) < 500:
                            tests.append(str(item.relative_to(path)))
            except OSError:
                pass

    return {
        "name": path.name,
        "id": path.name,
        "description": "",
        "has_contract": has_contract,
        "errors": errors,
        "requirements": requirements,
        "tests": sorted(tests),
    }


def list_projects():
    ensure_projects_root()
    result = []
    for path in sorted(PROJECTS_ROOT.iterdir()):
        if path.is_dir() and not path.is_symlink():
            item = inspect_project(path)
            config = path / "project.yaml"
            if config.is_file():
                try:
                    import yaml
                    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
                    item["id"] = data.get("project", {}).get("id", path.name)
                    item["description"] = data.get("project", {}).get("description", "")
                except (OSError, ValueError):
                    pass
            result.append(item)
    return result


@app.get("/")
def index():
    projects = list_projects()
    return render_template(
        "index.html",
        projects=projects,
        project_names=[p["name"] for p in projects],
        projects_root=PROJECTS_ROOT,
        analysis=None,
    )


@app.post("/projects/create")
def create():
    project_id = request.form.get("project_id", "").strip()
    name = request.form.get("project_name", "").strip()
    description = request.form.get("description", "").strip()

    if not valid_project_id(project_id):
        flash("Ungültige Projekt-ID.", "error")
        return redirect(url_for("index"))

    destination = PROJECTS_ROOT / project_id
    try:
        ensure_projects_root()
        create_project(TEMPLATE, destination, project_id)

        import yaml
        config_path = destination / "project.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["project"]["name"] = name
        if description:
            config["project"]["description"] = description
        config_path.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        errors = validate_imported_project(destination)
        if errors:
            raise ValueError("; ".join(errors))

        flash(f"Projekt '{project_id}' wurde erstellt.", "success")
    except Exception as exc:
        flash(f"Projekt konnte nicht erstellt werden: {exc}", "error")

    return redirect(url_for("index"))


@app.post("/projects/import")
def import_project():
    source = request.form.get("source", "").strip()
    project_id = request.form.get("project_id", "").strip()
    mode = request.form.get("mode", "local")

    if not valid_project_id(project_id):
        flash("Ungültige Projekt-ID.", "error")
        return redirect(url_for("index"))

    if mode not in ("local", "git"):
        abort(400)

    if mode == "git" and not source.startswith(("https://", "http://", "ssh://", "git@")):
        flash("Bitte eine HTTPS-, SSH- oder Git-URL angeben.", "error")
        return redirect(url_for("index"))

    destination = PROJECTS_ROOT / project_id

    try:
        ensure_projects_root()
        import_repository(Path(source), destination, clone=(mode == "git"))
        errors = validate_imported_project(destination)
        if errors:
            flash(
                "Repository importiert, aber Projektvertrag fehlt oder ist ungültig: "
                + "; ".join(errors),
                "error",
            )
        else:
            flash(f"Repository '{project_id}' wurde importiert und validiert.", "success")
    except Exception as exc:
        flash(f"Import fehlgeschlagen: {exc}", "error")

    return redirect(url_for("index"))



@app.post("/projects/analyze")
def analyze():
    project_name = request.form.get("project", "")
    if not valid_project_id(project_name):
        abort(400)

    path = PROJECTS_ROOT / project_name
    if not path.is_dir() or path.is_symlink():
        abort(404)

    result = inspect_project(path)
    result["plan"] = plan_project(path)
    result["fingerprint"] = None
    result["approval_token"] = None

    if (
        not result["errors"]
        and result["plan"].get("status") == "ready_for_review"
        and not result["plan"].get("errors")
    ):
        try:
            fingerprint = project_fingerprint(path)
            result["fingerprint"] = fingerprint
            result["approval_token"] = build_approval_token(
                project_name, fingerprint
            )
        except (OSError, ValueError) as exc:
            result["errors"].append(
                f"Projekt-Fingerprint konnte nicht erstellt werden: {exc}"
            )

    projects = list_projects()
    return render_template(
        "index.html",
        projects=projects,
        project_names=[p["name"] for p in projects],
        projects_root=PROJECTS_ROOT,
        analysis=result,
    )

@app.get("/projects/build/<job_id>/logs")
def build_logs(job_id):
    owner = session.get("build_session_id", "")
    cleanup_build_jobs()
    with BUILD_JOBS_LOCK:
        job = BUILD_JOBS.get(job_id)
        if job is None:
            abort(404)
        if not owner or not secrets.compare_digest(job["owner"], owner):
            abort(404)
        try:
            after = max(0, int(request.args.get("after", "0")))
        except ValueError:
            abort(400, "Ungültiger Ereignisindex.")

        event_offset = job.get("event_offset", 0)
        start = max(0, after - event_offset)

        return {
            "events": job["events"][start:],
            "event_offset": event_offset,
            "next": event_offset + len(job["events"]),
            "finished": job["finished"],
            "result": job["result"],
            "error": job["error"],
        }

@app.post("/projects/build")
def build_project():
    project_name = request.form.get("project", "").strip()
    if not valid_project_id(project_name):
        abort(400)

    path = PROJECTS_ROOT / project_name
    if not path.is_dir() or path.is_symlink():
        abort(404)

    # Die Freigabe wird zusätzlich serverseitig geprüft.
    if request.form.get("confirm_build") != "yes":
        abort(400, "Der Build wurde nicht ausdrücklich freigegeben.")

    result = inspect_project(path)
    plan = plan_project(path)
    result["plan"] = plan
    result["build_result"] = None

    submitted_fingerprint = request.form.get("fingerprint", "")
    submitted_token = request.form.get("approval_token", "")

    if (
        not re.fullmatch(r"[0-9a-f]{64}", submitted_fingerprint)
        or not re.fullmatch(r"[0-9a-f]{64}", submitted_token)
    ):
        abort(400, "Ungültige oder fehlende Build-Freigabe.")

    expected_token = build_approval_token(
        project_name, submitted_fingerprint
    )

    if not hmac.compare_digest(submitted_token, expected_token):
        abort(400, "Die Build-Freigabe ist ungültig.")

    try:
        current_fingerprint = project_fingerprint(path)
    except (OSError, ValueError) as exc:
        abort(400, f"Projektzustand kann nicht geprüft werden: {exc}")

    if not hmac.compare_digest(
        submitted_fingerprint, current_fingerprint
    ):
        abort(
            409,
            "Das Projekt wurde seit der Analyse verändert. "
            "Bitte erneut analysieren und den Build neu freigeben.",
        )

    # Keine Ausführung bei ungültigem Vertrag oder fehlerhaftem Ablaufplan.
    if result["errors"] or plan.get("status") != "ready_for_review" or plan.get("errors"):
        result["build_result"] = {
            "status": "blocked",
            "execution_performed": False,
            "flash_performed": False,
            "tests_executed": False,
            "commands": [],
            "errors": [
                "Build blockiert: Projektvalidierung oder Ablaufplan ist nicht fehlerfrei."
            ],
            "report_path": None,
        }
    else:
        owner = session.setdefault("build_session_id", secrets.token_urlsafe(32))
        job_id = uuid.uuid4().hex
        with BUILD_JOBS_LOCK:
            _cleanup_build_jobs_locked(reserve_slot=True)
            if len(BUILD_JOBS) >= MAX_BUILD_JOBS:
                abort(503, "Zu viele Build-Jobs laufen. Bitte später erneut versuchen.")

            BUILD_JOBS[job_id] = {
                "owner": owner,
                "events": [],
                "event_offset": 0,
                "created_at": time.time(),
                "finished_at": None,
                "finished": False,
                "result": None,
                "error": None,
            }

        thread = threading.Thread(
            target=run_build_job,
            args=(job_id, path),
            daemon=True,
        )
        thread.start()
        result["build_result"] = {
            "status": "running",
            "job_id": job_id,
            "execution_performed": True,
            "commands": [],
            "errors": [],
            "report_path": None,
        }

    return render_template(
        "index.html",
        projects=list_projects(),
        project_names=[p["name"] for p in list_projects()],
        projects_root=PROJECTS_ROOT,
        analysis=result,
    )


if __name__ == "__main__":
    ensure_projects_root()
    host = os.environ.get("EMBEDDED_LAB_HOST", "127.0.0.1")
    port = int(os.environ.get("EMBEDDED_LAB_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
