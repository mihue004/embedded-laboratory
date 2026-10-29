#!/usr/bin/env python3
"""Validate an Embedded Lab project configuration."""

import argparse
import sys
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "schemas" / "project.schema.yaml"


def validate_project(config_path: Path, schema_path: Path) -> list[str]:
    """Return validation errors; an empty list means the config is valid."""
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)

        with schema_path.open("r", encoding="utf-8") as stream:
            schema = yaml.safe_load(stream)

    except (OSError, yaml.YAMLError) as exc:
        return [f"Could not read YAML: {exc}"]

    if not isinstance(config, dict):
        return ["Project configuration must be a YAML mapping/object."]

    try:
        validator_class = jsonschema.validators.validator_for(schema)
        validator_class.check_schema(schema)
        validator = validator_class(schema)
    except (jsonschema.SchemaError, TypeError, ValueError) as exc:
        return [f"Invalid project schema: {exc}"]

    errors = sorted(
        validator.iter_errors(config),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )

    messages = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path)
        if not location:
            location = "<root>"
        messages.append(f"{location}: {error.message}")

    return messages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an Embedded Lab project.yaml file."
    )
    parser.add_argument("config", type=Path, help="Path to project YAML file")
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="Path to the project schema",
    )
    args = parser.parse_args()

    errors = validate_project(args.config, args.schema)

    if errors:
        print(f"INVALID: {args.config}")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"VALID: {args.config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
