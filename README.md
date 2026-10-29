# Embedded Lab

Embedded Lab is a modular development and test platform for embedded
software projects.

The long-term goal is to automate the workflow from requirements to
implementation, build, hardware-based testing, and test reporting.

## Goals

- Reusable project templates for different embedded platforms
- Configurable automated tests
- Hardware-independent test orchestration where possible
- Integration with GitHub and Git-based development workflows
- AI-assisted code generation and modification
- Automated builds, hardware tests, and structured reports

## Current status

The initial hardware test setup uses a Raspberry Pi as the host and
two Raspberry Pi Pico boards for signal generation and measurement.

The current setup is an initial implementation of the hardware testing
layer. The broader development orchestration and AI integration are
planned components.

## Repository structure

- `docs/` - Architecture, setup instructions, and design decisions
- `firmware/` - Firmware for the test hardware
- `host/` - Host-side test execution tools
- `tests/` - Test definitions and examples
- `artifacts/` - Locally generated test results and other artifacts
- `pico-sdk/` - Raspberry Pi Pico SDK Git submodule

## Development principles

- Keep project requirements separate from implementation details.
- Make test conditions configurable wherever possible.
- Keep generated files out of source control unless explicitly required.
- Preserve traceability between requirements, code changes, builds, and tests.
