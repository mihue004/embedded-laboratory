# Embedded Lab

Embedded Lab is a modular development and test platform for embedded software projects.

Its long-term goal is to automate the development workflow from project requirements through implementation and build execution to hardware-based testing, evaluation, and reporting.

The platform is designed to support different embedded targets while keeping project management, test orchestration, and hardware-specific functionality as independent components.

## Architecture and Hardware

The platform consists of three main areas:

- **Host system:** A Raspberry Pi running the web application, project management, build orchestration, and test execution tools.
- **Test hardware:** Raspberry Pi Pico boards used as independently controllable devices for signal generation and measurement.
- **Embedded projects:** Separate projects containing firmware, requirements, configuration, and test definitions.

The current hardware setup consists of:

- Raspberry Pi 4 as the host system
- Two Raspberry Pi Pico 2 boards
- Raspberry Pi Pico SDK for firmware development

The hardware abstraction is intended to allow additional microcontroller platforms and test devices to be integrated in the future.

## Current Features

The current implementation includes:

- Flask-based web interface
- Creation of projects from reusable templates
- Import of existing Git repositories
- Project configuration and contract validation
- Requirement inspection and test traceability checks
- Test case validation
- Build execution through the web interface
- Build status and command output reporting
- Serial-based hardware test execution
- Structured JSON test reports

The hardware test runner communicates with connected devices over serial interfaces and executes defined test steps.

Build execution currently supports configured CMake, Make, and PlatformIO projects, subject to the required tools being installed.

## Technical Requirements

### Minimum Requirements

- Python 3.10 or newer
- Git
- pip
- A supported operating system (Linux is the current development target)
- Additional build tools depending on the selected embedded project

For Pico SDK projects, the following tools are required:

- CMake
- Ninja
- ARM GNU Toolchain (`arm-none-eabi-gcc`)
- Raspberry Pi Pico SDK

Python 3.10 is the intended minimum for the development and test environment. Compatibility with all supported Python versions and operating systems is not yet fully verified.

### Reference Development Environment

The platform is currently developed and tested using:

- Raspberry Pi 4
- Debian GNU/Linux 13
- Python 3.13
- Raspberry Pi Pico SDK 2.3.1
- CMake
- Ninja
- ARM GNU Toolchain

Python dependencies are defined in:

- `requirements.txt` - Runtime dependencies
- `requirements-dev.txt` - Additional development and test dependencies

## Installation

Clone the repository including its submodules:

```bash
git clone --recurse-submodules https://github.com/mihue004/embedded-laboratory.git
cd embedded-laboratory
```

If the repository was cloned without submodules:

```bash
git submodule update --init --recursive
```

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements-dev.txt
```

Install the required system build tools using the package manager of your host system.

For Pico SDK projects, CMake, Ninja, and the ARM GNU Toolchain must be available.

## Starting the Web Interface

Start the application from the repository root:

```bash
source .venv/bin/activate
python host/webapp/app.py
```

By default, the web application listens on `127.0.0.1` and port `5000`.

The host and port can be configured through environment variables:

- `EMBEDDED_LAB_HOST`
- `EMBEDDED_LAB_PORT`

The project storage directory can be configured using `EMBEDDED_PROJECTS_ROOT`. If not specified, projects are stored in `~/embedded-projects`.

## Running Unit Tests

Activate the virtual environment and execute:

```bash
python -m pytest
```

The test configuration is defined in `pytest.ini`.

## Limitations and Planned Development

The platform is under active development. The following capabilities are planned or require further implementation:

- **AI integration:** AI-assisted project analysis, code generation, and modification.
- **Automated development workflow:** Iterative requirement evaluation, implementation, build execution, and hardware testing.
- **Hardware discovery:** Automatic detection and identification of connected test devices.
- **Hardware selection:** Selecting available Pico devices through the web interface instead of relying on hardcoded device identifiers.
- **System settings:** A central settings area for managing connected devices and system-wide configuration.
- **Extended hardware abstraction:** Support for additional microcontrollers, measurement devices, and debugging interfaces.
- **Extended signal testing:** More advanced measurements for PWM, interrupts, timing behavior, and fast digital signals.
- **Simulation:** Logical test execution and fault-case simulation before testing on physical hardware.
- **Automated flashing:** Integration of firmware flashing and device management into the orchestrated workflow.

These features represent development goals and are not all part of the current implementation.

## Repository Structure

```text
embedded-laboratory/
├── config/                 # Platform and system configuration
├── core/
│   ├── orchestrator/       # Build and test orchestration
│   └── project_manager/    # Project creation and import
├── docs/
│   └── architecture/       # Architecture documentation
├── firmware/               # Test hardware firmware
├── host/
│   ├── testbench/          # Hardware test execution
│   └── webapp/             # Web interface
├── schemas/                # Project and test schemas
├── staging/                # Project staging area
├── templates/              # Reusable embedded project templates
├── tests/
│   ├── examples/           # Example test definitions
│   └── unit/               # Unit tests
├── artifacts/              # Locally generated results
├── pico-sdk/               # Raspberry Pi Pico SDK submodule
├── requirements.txt
├── requirements-dev.txt
└── pytest.ini
```

## Development Principles

- Keep project requirements separate from implementation details.
- Make test conditions configurable wherever possible.
- Separate hardware-specific functionality from the central orchestration logic.
- Keep generated files out of source control unless explicitly required.
- Preserve traceability between requirements, code changes, builds, and tests.
- Require explicit approval for operations that execute builds or interact with physical hardware.
