# Hardware Abstraction and Device Capabilities

## Purpose

Embedded Lab must support different test devices without assigning
permanent roles to individual devices.

A device may provide signal generation, signal measurement, GPIO,
interrupt capture, UART, SPI, I2C, or other capabilities. The available
capabilities depend on the device hardware, firmware, configuration,
pin assignment, and resource conflicts.

## Separation of responsibilities

### Device profiles

Describe a device class and its potential capabilities, including
supported operating ranges, relevant limits, and resource constraints.

A capability must not be advertised as available unless the installed
firmware and hardware actually support it.

### Device instances

Identify individual connected devices independently of their roles.
Instance information includes device identity, connection details,
firmware version, reported capabilities, and current availability.

Connection details such as USB serial paths must not be used as
permanent device identities.

### Test assignments

A test declares the capabilities it requires. The orchestrator assigns
available devices to those requirements and checks whether the requested
configuration is feasible.

Roles such as signal generator and analyzer are temporary assignments
within a test, not permanent properties of a device.

### Hardware setup profiles

Describe physical connections and constraints between devices and the
device under test. Examples include signal loopback wiring, shared
ground, voltage compatibility, and reserved pins.

A setup profile is separate from a device profile.

## Capability model

Capabilities must be extensible. Initial capability families include:

- GPIO input and output
- Digital signal generation
- PWM generation
- Frequency, duty-cycle, and pulse-width measurement
- Interrupt and edge capture
- UART
- SPI
- I2C
- Timing and synchronization

Each capability may declare operating limits, pin requirements,
resource requirements, and supported configuration options.

## Resource allocation

Before a test starts, the orchestrator checks pin conflicts, peripheral
availability, resource conflicts, electrical compatibility, and
required connections.

A device must not be assigned incompatible operations concurrently.

## Firmware interface

Device-specific communication protocols are isolated behind a common
host-side interface. The orchestrator must not depend directly on
device-specific serial commands.

Firmware capabilities are discovered or validated before a test runs.
Unsupported operations must fail explicitly and safely.

## Safety and traceability

Tests must not assume that a pin is electrically safe to drive.
Voltage levels, pin direction, wiring, and possible contention must be
considered before execution.

Every test report records the assigned devices, firmware versions,
relevant configuration, and measured results.

## Initial implementation

The first implementation uses the existing two Raspberry Pi Pico 2
boards. Their current firmware and tested signal-measurement workflow
must remain functional during the architectural transition.

The abstraction must allow additional device types, controllers,
measurement equipment, and communication backends without redesigning
the test orchestration layer.
