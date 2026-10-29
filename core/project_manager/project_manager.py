#!/usr/bin/env python3
"""Create and import Embedded Lab projects without executing project code."""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from validate_project import DEFAULT_SCHEMA, validate_project


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = ROOT / "templates" / "pico-sdk"


def create_project(
    template: Path,
    destination: Path,
    project_id: str,
) -> None:
    """Create a complete project by copying a template directory."""
    template = template.expanduser().resolve()
    destination = destination.expanduser().resolve()

    if not template.is_dir():
        raise ValueError(f"Template directory does not exist: {template}")

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", project_id):
        raise ValueError(
            "Project ID must contain lowercase letters, digits and single hyphens."
        )

    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}")

    template_config = template / "project.yaml"
    if not template_config.is_file():
        raise ValueError(f"Template has no project.yaml: {template}")

    template_errors = validate_project(template_config, DEFAULT_SCHEMA)
    if template_errors:
        raise ValueError(
            "Template project.yaml is invalid: " + "; ".join(template_errors)
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        template,
        destination,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".venv", "venv", "build", "artifacts"
        ),
    )

    try:
        config_path = destination / "project.yaml"
        content = config_path.read_text(encoding="utf-8")

        import yaml

        config = yaml.safe_load(content)
        config["project"]["id"] = project_id
        config_path.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        errors = validate_project(config_path, DEFAULT_SCHEMA)
        if errors:
            raise ValueError(
                "Created project is invalid: " + "; ".join(errors)
            )
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def import_repository(
    source: Path,
    destination: Path,
    clone: bool = False,
) -> None:
    """Import a project and remove the new destination if its contract is invalid."""
    destination = destination.expanduser().resolve()
    source_text = str(source)
    source_path = source.expanduser()

    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}")

    try:
        if clone:
            subprocess.run(
                ["git", "clone", "--", source_text, str(destination)],
                check=True,
            )
        else:
            source_path = source_path.resolve()
            if not source_path.is_dir():
                raise ValueError(
                    f"Source directory does not exist: {source_path}"
                )

            if source_path == destination or source_path in destination.parents:
                raise ValueError(
                    "Destination must not be inside the source directory."
                )

            shutil.copytree(
                source_path,
                destination,
                ignore=shutil.ignore_patterns(
                    ".git",
                    "__pycache__",
                    ".venv",
                    "venv",
                    "build",
                    "artifacts",
                ),
            )

        errors = validate_imported_project(destination)
        if errors:
            raise ValueError(
                "Imported project has an invalid contract: "
                + "; ".join(errors)
            )

    except Exception:
        # Only remove the destination created by this import attempt.
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination, ignore_errors=True)
        raise


def validate_imported_project(project_dir: Path) -> list[str]:
    """Validate the imported project's contract."""
    config_path = project_dir / "project.yaml"
    return validate_project(config_path, DEFAULT_SCHEMA)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create and import Embedded Lab projects."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("project_id")
    create_parser.add_argument("destination", type=Path)
    create_parser.add_argument(
        "--template", type=Path, default=DEFAULT_TEMPLATE
    )

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("source")
    import_parser.add_argument("destination", type=Path)
    import_parser.add_argument(
        "--git",
        action="store_true",
        help="Clone source as a Git URL instead of copying a local directory.",
    )

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("project_dir", type=Path)

    args = parser.parse_args()

    try:
        if args.command == "create":
            create_project(
                args.template, args.destination, args.project_id
            )
            project_dir = args.destination.expanduser().resolve()

        elif args.command == "import":
            import_repository(
                Path(args.source),
                args.destination,
                clone=args.git,
            )
            project_dir = args.destination.expanduser().resolve()

        else:
            project_dir = args.project_dir.expanduser().resolve()

        errors = validate_imported_project(project_dir)
        if errors:
            print(f"INVALID: {project_dir / 'project.yaml'}")
            for error in errors:
                print(f"  - {error}")
            return 1

        print(f"VALID: {project_dir}")
        return 0

    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
