# Hardware tests

Hardware tests are executed by the Embedded Lab host against a connected
device. Test procedures must declare their equipment and acceptance criteria.

## HW-SERIAL-001

1. Flash the firmware to a Raspberry Pi Pico 2.
2. Connect to its USB serial interface.
3. Verify that the startup status message appears periodically.

Acceptance criterion: the expected message is received repeatedly.
