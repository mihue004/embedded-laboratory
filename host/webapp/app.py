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

from flask import Flask, abort, flash, redirect, render_template_string, request, session, url_for

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
app.secret_key = os.environ.get("EMBEDDED_LAB_SESSION_SECRET") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
)

BUILD_JOBS = {}
BUILD_JOBS_LOCK = threading.Lock()

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

PAGE = """
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Embedded Lab</title>
<style>
:root {
  color-scheme: dark;
  font-family: system-ui, sans-serif;
  background: #121612;
  color: #e8eee7;
}
* { box-sizing: border-box; }
body { margin: 0; }
header { padding: 24px max(20px, calc((100% - 1100px)/2)); background: #1b241b; border-bottom: 1px solid #354435; }
main { max-width: 1100px; margin: auto; padding: 24px 20px 60px; }
h1 { margin: 0; font-size: 1.7rem; }
h2 { font-size: 1.2rem; margin-top: 0; }
p, .muted { color: #b6c2b3; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
.panel { background: #1b211b; border: 1px solid #354435; border-radius: 10px; padding: 20px; margin-bottom: 22px; min-width: 0; }
label { display: block; margin: 12px 0 5px; }
input, select, textarea, button { font: inherit; }
input, select, textarea { width: 100%; padding: 10px; background: #111711; color: #e8eee7; border: 1px solid #536353; border-radius: 5px; }
textarea { min-height: 90px; resize: vertical; }
button { margin-top: 14px; padding: 10px 14px; background: #56b04c; color: #101610; border: 0; border-radius: 5px; cursor: pointer; font-weight: 650; }
button:hover { background: #71e864; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 8px; text-align: left; vertical-align: top; border-bottom: 1px solid #354435; overflow-wrap: anywhere; }
th { color: #b6c2b3; }
code { overflow-wrap: anywhere; }
.notice { padding: 12px; border: 1px solid #536353; border-radius: 5px; margin: 12px 0; }
.error { border-color: #bd7168; }
.success { border-color: #56b04c; }
ul { padding-left: 22px; }
small { color: #b6c2b3; }
@media(max-width: 600px) { main { padding: 16px 12px; } .panel { padding: 14px; } }
</style>
</head>
<body>
<header>
  <h1>Embedded Lab</h1>
  <p>Embedded-Entwicklung, Projektanalyse und nachvollziehbare Tests</p>
</header>
<main>
  {% for category, message in get_flashed_messages(with_categories=true) %}
    <div class="notice {{ category }}">{{ message }}</div>
  {% endfor %}

  <section class="panel">
    <h2>Projektübersicht</h2>
    <p>Projektablage: <code>{{ projects_root }}</code></p>
    {% if projects %}
    <table>
      <thead><tr><th>Projekt</th><th>Validierung</th><th>Beschreibung</th></tr></thead>
      <tbody>
      {% for project in projects %}
        <tr>
          <td><strong>{{ project.name }}</strong><br><small>{{ project.id }}</small></td>
          <td>
            {% if project.errors %}
              <span>Ungültig</span>
              <ul>{% for error in project.errors %}<li>{{ error }}</li>{% endfor %}</ul>
            {% elif project.has_contract %}
              Gültig
            {% else %}
              Kein Projektvertrag
            {% endif %}
          </td>
          <td>{{ project.description or "Keine Beschreibung" }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    {% else %}
      <p>Noch keine Projekte vorhanden.</p>
    {% endif %}
  </section>

  <div class="grid">
    <section class="panel">
      <h2>Neues Projekt</h2>
      <form method="post" action="{{ url_for('create') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
        <label for="project_id">Projekt-ID</label>
        <input id="project_id" name="project_id" required pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="mein-embedded-projekt">
        <label for="project_name">Projektname</label>
        <input id="project_name" name="project_name" required placeholder="Mein Embedded-Projekt">
        <label for="description">Beschreibung</label>
        <textarea id="description" name="description" placeholder="Zweck, Funktionen und Anforderungen"></textarea>
        <button type="submit">Projekt erstellen</button>
      </form>
      <small>Verwendet das vorhandene Pico-SDK-Template.</small>
    </section>

    <section class="panel">
      <h2>Repository importieren</h2>
      <form method="post" action="{{ url_for('import_project') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
        <label for="source">Lokaler Pfad oder Git-URL</label>
        <input id="source" name="source" required placeholder="/home/pi/mein-repository oder https://...">
        <label for="project_id_import">Neue Projekt-ID</label>
        <input id="project_id_import" name="project_id" required pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="importiertes-projekt">
        <label for="import_mode">Quelle</label>
        <select id="import_mode" name="mode">
          <option value="local">Lokales Verzeichnis kopieren</option>
          <option value="git">Git-Repository klonen</option>
        </select>
        <button type="submit">Importieren</button>
      </form>
      <small>Bestehende Zielverzeichnisse werden nicht überschrieben. Importierter Code wird nicht ausgeführt.</small>
    </section>
  </div>

  <section class="panel">
    <h2>Projektanalyse</h2>
    <p>Prüft Projektvertrag, Anforderungen, Build-Konfiguration und Testverzeichnisse. Es werden keine Builds oder Tests gestartet und keine Projektdateien verändert.</p>
    <form method="post" action="{{ url_for('analyze') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
      <label for="analysis_project">Projekt</label>
      <select id="analysis_project" name="project" required>
        {% for project in project_names %}
          <option value="{{ project }}">{{ project }}</option>
        {% endfor %}
      </select>
      <button type="submit">Projekt analysieren</button>
    </form>
    {% if analysis %}
      <div class="notice">
        <strong>Analyse: {{ analysis.name }}</strong>
        <p>Projektvertrag: {{ "vorhanden" if analysis.has_contract else "fehlt" }}</p>
        {% if analysis.errors %}
          <strong>Validierungsfehler</strong>
          <ul>{% for error in analysis.errors %}<li>{{ error }}</li>{% endfor %}</ul>
        {% endif %}
        <p>Anforderungsdatei: {{ analysis.requirements or "nicht konfiguriert" }}</p>
        <p>Gefundene Testdateien: {{ analysis.tests|length }}</p>
        <ul>{% for test in analysis.tests %}<li><code>{{ test }}</code></li>{% else %}<li>Keine Testdateien gefunden.</li>{% endfor %}</ul>
        <p>Hinweis: Das Vorhandensein von Tests beweist weder deren Vollständigkeit noch die Korrektheit der Firmware.</p>

        {% if analysis.plan %}
          <hr>
          <h3>Ablaufplan</h3>
          <p><strong>Status:</strong> {{ analysis.plan.status }}</p>
          <p><strong>Modus:</strong> Nur Planung – keine Ausführung</p>
          <p><strong>Build oder Tests ausgeführt:</strong> Nein</p>
          <p><strong>Firmware geflasht:</strong> Nein</p>

          {% if analysis.plan.errors %}
            <strong>Fehler</strong>
            <ul>{% for error in analysis.plan.errors %}<li>{{ error }}</li>{% endfor %}</ul>
          {% endif %}

          {% if analysis.plan.warnings %}
            <strong>Hinweise</strong>
            <ul>{% for warning in analysis.plan.warnings %}<li>{{ warning }}</li>{% endfor %}</ul>
          {% endif %}

          <h4>Prüfergebnisse</h4>
          <ul>
            {% for key, check in analysis.plan.checks.items() %}
              <li>
                <strong>{{ key }}:</strong>
                {% if check.status is defined %}
                  {{ check.status }}
                {% else %}
                  Details siehe Unterpunkte
                {% endif %}
                {% if check.count is defined %}
                  ({{ check.count }} Anforderungen)
                {% endif %}
                {% if check.errors %}
                  <ul>{% for error in check.errors %}<li><strong>Fehler:</strong> {{ error }}</li>{% endfor %}</ul>
                {% endif %}
                {% if check.warnings %}
                  <ul>{% for warning in check.warnings %}<li><strong>Hinweis:</strong> {{ warning }}</li>{% endfor %}</ul>
                {% endif %}
              </li>
            {% endfor %}
          </ul>

          {% if analysis.plan.checks.traceability %}
            {% set trace = analysis.plan.checks.traceability %}
            <h4>Traceability – Anforderungsabdeckung</h4>
            <p>
              Status: <strong>{{ trace.status }}</strong> –
              {{ trace.covered_requirements|length }} von
              {{ trace.requirement_count }} Anforderungen mit auflösbarem
              Hardwaretest.
              {{ trace.test_case_count }} Testfälle gefunden.
            </p>

            {% if trace.covered_requirements %}
              <p><strong>Abgedeckte Anforderungen</strong></p>
              <ul>{% for item in trace.covered_requirements %}<li>{{ item }}</li>{% endfor %}</ul>
            {% endif %}

            {% if trace.uncovered_requirements %}
              <p><strong>Nicht abgedeckte Anforderungen</strong></p>
              <ul>{% for item in trace.uncovered_requirements %}<li>{{ item }}</li>{% endfor %}</ul>
            {% endif %}

            {% if trace.unresolved_test_references %}
              <p><strong>Nicht auflösbare Testreferenzen</strong></p>
              <ul>{% for item in trace.unresolved_test_references %}
                <li>Anforderung {{ item.requirement_id }} → Test {{ item.test_id }}</li>
              {% endfor %}</ul>
            {% endif %}

            {% if trace.unknown_requirement_references %}
              <p><strong>Unbekannte Requirement-Referenzen</strong></p>
              <ul>{% for item in trace.unknown_requirement_references %}
                <li>Test {{ item.test_id }} → Anforderung {{ item.requirement_id }}</li>
              {% endfor %}</ul>
            {% endif %}
          {% endif %}

          {% if analysis.plan.checks.requirements.requirements %}
            <h4>Erkannte Anforderungen</h4>
            <ul>
              {% for requirement in analysis.plan.checks.requirements.requirements %}
                <li>
                  <strong>{{ requirement.id or "Ohne ID" }}:</strong>
                  {{ requirement.description or "Keine Beschreibung" }}
                </li>
              {% endfor %}
            </ul>
          {% endif %}

          <h4>Geplante Schritte</h4>
          <ul>
            {% for step in analysis.plan.steps %}
              <li>
                <strong>{{ step.id }}:</strong> {{ step.description }}
                <br><small>Status: {{ step.status }}
                {% if step.requires_approval %} – Freigabe erforderlich{% endif %}
                {% if step.requires_explicit_approval %} – ausdrückliche Freigabe erforderlich{% endif %}
                </small>
              </li>
            {% endfor %}
          </ul>

          {% if analysis.plan.status == "ready_for_review" and not analysis.errors and not analysis.plan.errors %}
            <div class="notice">
              <strong>Build manuell freigeben</strong>
              <p>Es werden Build-Kommandos für dieses Projekt ausgeführt. Es wird keine Firmware geflasht und es werden keine Tests gestartet.</p>
              <form method="post" action="{{ url_for('build_project') }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                <input type="hidden" name="project" value="{{ analysis.id }}">
                <input type="hidden" name="fingerprint"
                       value="{{ analysis.fingerprint }}">
                <input type="hidden" name="approval_token"
                       value="{{ analysis.approval_token }}">
                <label>
                  <input type="checkbox" name="confirm_build" value="yes" required style="width:auto">
                  Ich erlaube ausdrücklich, den Build für dieses Projekt auszuführen.
                </label>
                <button type="submit">Build jetzt ausführen</button>
              </form>
            </div>
          {% endif %}
        {% endif %}

        {% if analysis.build_result %}
          <hr>
          <h3>Build-Ergebnis</h3>
          <p><strong>Status:</strong> <span id="build-status">{{ analysis.build_result.status }}</span></p>
          <p><strong>Build ausgeführt:</strong> {{ "Ja" if analysis.build_result.execution_performed else "Nein" }}</p>
          <p><strong>Firmware geflasht:</strong> Nein</p>
          <p><strong>Tests ausgeführt:</strong> Nein</p>

          {% if analysis.build_result.errors %}
            <strong>Fehler und Hinweise</strong>
            <ul>{% for error in analysis.build_result.errors %}<li>{{ error }}</li>{% endfor %}</ul>
          {% endif %}

          {% if analysis.build_result.report_path %}
            <p>Bericht: <code>{{ analysis.build_result.report_path }}</code></p>
          {% endif %}

          {% for command in analysis.build_result.commands %}
            <div class="notice">
              <strong>Kommando – Status: {{ command.status }}</strong>
              <p><code>{{ command.argv | join(" ") }}</code></p>
              {% if command.returncode is not none %}
                <p>Rückgabecode: {{ command.returncode }}</p>
              {% endif %}
              {% if command.stdout %}
                <details>
                  <summary>Standardausgabe</summary>
                  <pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:400px;overflow:auto">{{ command.stdout[:12000] }}</pre>
                </details>
              {% endif %}
              {% if command.stderr %}
                <details open>
                  <summary>Fehlerausgabe</summary>
                  <pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:400px;overflow:auto">{{ command.stderr[:12000] }}</pre>
                </details>
              {% endif %}
            </div>
          {% endfor %}
        {% endif %}
      </div>
    {% endif %}
  </section>
  <p class="muted"><small>Erste Entwicklungsstufe: KI-Backend, Freigabeworkflow und autonome Build-/Testschleifen sind noch nicht aktiviert. Kein automatisches Flashen.</small></p>
</main>
{% if analysis.build_result and analysis.build_result.job_id %}
<script>
(async () => {
  const url = {{ url_for('build_logs', job_id=analysis.build_result.job_id) | tojson }};
  const status = document.getElementById('build-status');
  const resultSection = [...document.querySelectorAll('h3')]
    .find(element => element.textContent.trim() === 'Build-Ergebnis');

  if (!resultSection || !status) return;

  const container = document.createElement('div');
  container.id = 'live-build-commands';
  resultSection.insertAdjacentElement('afterend', container);

  const commands = new Map();
  let count = 0;

  function getCommand(index, argv) {
    if (commands.has(index)) return commands.get(index);

    const card = document.createElement('div');
    card.className = 'notice';

    const heading = document.createElement('strong');
    heading.textContent = 'Kommando – Status: läuft';

    const commandLine = document.createElement('p');
    const code = document.createElement('code');
    code.textContent = Array.isArray(argv) ? argv.join(' ') : '';
    commandLine.appendChild(code);

    const output = document.createElement('pre');
    output.style.cssText =
      'white-space:pre-wrap;overflow-wrap:anywhere;max-height:400px;overflow:auto';

    card.append(heading, commandLine, output);
    container.appendChild(card);

    const item = { heading, output };
    commands.set(index, item);
    return item;
  }

  while (true) {
    try {
      const response = await fetch(`${url}?after=${count}`);
      if (!response.ok) {
        status.textContent = 'Fehler beim Abrufen der Build-Ausgabe';
        break;
      }

      const data = await response.json();

      for (const event of data.events) {
        if (event.type === 'command_started') {
          getCommand(event.command_index, event.argv);
        } else if (event.type === 'command_output') {
          const item = getCommand(event.command_index);
          item.output.textContent += `[${event.stream}] ${event.line}\n`;
          item.output.scrollTop = item.output.scrollHeight;
        } else if (event.type === 'command_finished') {
          const item = getCommand(event.command_index, event.argv);
          item.heading.textContent =
            `Kommando – Status: ${event.status}` +
            (event.returncode !== undefined
              ? ` (Rückgabecode: ${event.returncode})`
              : '');
        }
      }

      count = data.next;

      if (data.finished) {
        if (data.error) {
          status.textContent = `Fehler: ${data.error}`;
        } else if (data.result) {
          status.textContent = data.result.status;
        }
        break;
      }
    } catch (error) {
      status.textContent = `Verbindungsfehler: ${error}`;
      break;
    }

    await new Promise(resolve => setTimeout(resolve, 500));
  }
})();
</script>
{% endif %}
</body>
</html>
"""


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
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(400, "Ungültiges oder abgelaufenes Formular-Token.")


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token()}

def run_build_job(job_id, project_path):
    def on_event(event):
        with BUILD_JOBS_LOCK:
            BUILD_JOBS[job_id]["events"].append(event)

    try:
        result = execute_build(
            project_path,
            approved=True,
            event_callback=on_event,
        )
        with BUILD_JOBS_LOCK:
            BUILD_JOBS[job_id]["result"] = result
            BUILD_JOBS[job_id]["finished"] = True
    except Exception as exc:
        with BUILD_JOBS_LOCK:
            BUILD_JOBS[job_id]["error"] = str(exc)
            BUILD_JOBS[job_id]["finished"] = True

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
    return render_template_string(
        PAGE,
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
    return render_template_string(
        PAGE,
        projects=projects,
        project_names=[p["name"] for p in projects],
        projects_root=PROJECTS_ROOT,
        analysis=result,
    )

@app.get("/projects/build/<job_id>/logs")
def build_logs(job_id):
    owner = session.get("build_session_id", "")
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

        return {
            "events": job["events"][after:],
            "next": len(job["events"]),
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
            BUILD_JOBS[job_id] = {
                "owner": owner,
                "events": [],
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

    return render_template_string(
        PAGE,
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
