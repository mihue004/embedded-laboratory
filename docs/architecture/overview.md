# Embedded Lab Architecture

## 1. Purpose

Embedded Lab is a reusable development and test platform for embedded
software projects.

The platform shall support a workflow from requirements and repository
management through AI-assisted implementation, compilation, automated
testing, and result reporting.

## 2. Architectural components

### Project Manager
Loads project repositories and reads their project configuration.

### Orchestrator
Coordinates build, test, analysis, and reporting steps.

### AI Integration
Provides controlled access to AI-assisted requirements analysis,
code generation, and correction proposals.

### Build System
Builds projects using their declared toolchain and build system.

### Test Framework
Executes configurable test cases and evaluates their acceptance criteria.

### Hardware Abstraction
Provides a common interface to physical test equipment and controllers.

### Reporting
Collects build logs, measurements, test results, and requirement coverage.

### Integrations
Connects the platform to GitHub, GitLab, and later CI systems.

## 3. Separation of concerns

The platform implementation must remain separate from the embedded
project being developed.

Project-specific settings, requirements, source code, build configuration,
and tests belong to the individual project.

Reusable orchestration, hardware interfaces, test execution, and reporting
belong to Embedded Lab.

## 4. Initial implementation

The initial hardware test station consists of a Raspberry Pi host and
two Raspberry Pi Pico boards.

The existing signal generator and signal analyzer serve as the first
hardware backend. Their current capabilities must not limit the overall
project configuration or architecture.

## 5. Intended development workflow

1. Load a project repository.
2. Validate its project configuration.
3. Read and analyze its requirements.
4. Generate or modify implementation code when requested.
5. Build the project.
6. Execute applicable software and hardware tests.
7. Associate results with requirements.
8. Produce a report and determine the next action.

AI-generated changes and test results must remain traceable.
A successful build alone does not establish that requirements are fulfilled.
