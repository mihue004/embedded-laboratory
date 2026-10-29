# Project Contract

## Purpose

Every project managed by Embedded Lab must provide a machine-readable
description of its structure, target platform, build process, requirements,
and tests.

The initial contract will be defined in `project.yaml`.

## Initial fields

- `schema_version`: version of the project contract
- `project`: project name and version
- `target`: controller and embedded platform
- `build`: build system and relevant configuration
- `requirements`: location of the requirement definitions
- `testing`: test locations and required test capabilities
- `artifacts`: locations for generated outputs

## Design principles

- Project configuration must be independent of the orchestrator implementation.
- Build and test settings must be explicit and machine-readable.
- Platform-specific behavior must be isolated behind defined interfaces.
- Existing project defaults should be reusable through templates.
- Requirements, code changes, builds, and test results must be traceable.
- The contract must be versioned and validated before execution.

## Initial scope

The first project template will use CMake and the Raspberry Pi Pico SDK.

The contract must not be limited to the Pico platform. Additional build
systems and targets, including PlatformIO and other microcontrollers,
must be possible without redesigning the overall architecture.

The exact schema and validation rules will be implemented in a later step.
