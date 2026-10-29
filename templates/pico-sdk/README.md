# Embedded Lab Pico SDK Template

Starter project for the Raspberry Pi Pico 2 (RP2350).

## Build

The template expects the Embedded Lab repository's `pico-sdk` directory
at the relative path `../../pico-sdk`.

From this project's root:

    cmake -S . -B build
    cmake --build build

The resulting UF2 firmware can be flashed to the Pico 2 using its BOOTSEL
USB mass-storage interface.

Project settings and requirements are defined in `project.yaml` and
`requirements/requirements.yaml`.
