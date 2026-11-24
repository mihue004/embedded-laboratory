import threading
import time

import serial


class DeviceCommunication:
    BAUDRATE = 115200
    SERIAL_TIMEOUT = 0.2
    COMMAND_TIMEOUT = 5.0

    def __init__(self):
        self._connections = {}
        self._connections_lock = threading.RLock()

    def connect(self, device_id, port):
        with self._connections_lock:
            existing = self._connections.get(device_id)

            if existing is not None:
                if existing["port"] == port and existing["serial"].is_open:
                    return True

                self.disconnect(device_id)

            connection = serial.Serial(
                port=port,
                baudrate=self.BAUDRATE,
                timeout=self.SERIAL_TIMEOUT,
                write_timeout=2
            )

            self._connections[device_id] = {
                "port": port,
                "serial": connection,
                "lock": threading.RLock()
            }

            return True

    def disconnect(self, device_id):
        with self._connections_lock:
            connection = self._connections.pop(device_id, None)

            if connection is not None:
                try:
                    connection["serial"].close()
                except serial.SerialException:
                    pass

    def disconnect_all(self):
        with self._connections_lock:
            device_ids = list(self._connections)

        for device_id in device_ids:
            self.disconnect(device_id)

    def is_connected(self, device_id):
        with self._connections_lock:
            connection = self._connections.get(device_id)

            return (
                connection is not None
                and connection["serial"].is_open
            )

    def _get_connection(self, device_id):
        with self._connections_lock:
            connection = self._connections.get(device_id)

        if connection is None or not connection["serial"].is_open:
            raise RuntimeError("Device is not connected")

        return connection

    def _write_line(self, connection, command):
        device = connection["serial"]

        device.write((command + "\n").encode("ascii"))
        device.flush()

    def _read_line(self, connection, deadline):
        device = connection["serial"]

        while time.monotonic() < deadline:
            raw = device.readline()

            if not raw:
                continue

            line = raw.decode("ascii", errors="replace").strip()

            if not line:
                continue

            # Asynchrone Analyzer-Messwerte sind keine
            # Antworten auf Konfigurationsbefehle.
            if line.startswith("MEASURE,"):
                continue

            if line.startswith("ERR,"):
                raise RuntimeError(line)

            return line

        raise TimeoutError("Timeout waiting for Pico response")

    def _wait_for(self, connection, expected):
        deadline = time.monotonic() + self.COMMAND_TIMEOUT

        while True:
            line = self._read_line(connection, deadline)

            if line == expected:
                return

    @staticmethod
    def _parse_config(lines):
        pins = [None] * 30
        i2c = [None] * 2
        spi = [None] * 2
        uart = [None] * 2

        version = None

        for line in lines:
            fields = line.split(",")

            if fields[0] != "CONFIG":
                continue

            if fields[1] == "BEGIN":
                if len(fields) != 3:
                    raise RuntimeError("Invalid configuration header")

                version = int(fields[2])

            elif fields[1] == "PIN":
                if len(fields) != 9:
                    raise RuntimeError("Invalid GPIO configuration")

                pin = int(fields[2])

                if not 0 <= pin < len(pins) or pins[pin] is not None:
                    raise RuntimeError("Invalid or duplicate GPIO")

                pins[pin] = {
                    "pin": pin,
                    "function": int(fields[3]),
                    "peripheral_instance": int(fields[4]),
                    "pio_priority": int(fields[5]),
                    "pull": int(fields[6]),
                    "initial_level": int(fields[7]),
                    "input_filter_us": int(fields[8])
                }

            elif fields[1] == "I2C":
                if len(fields) != 4:
                    raise RuntimeError("Invalid I2C configuration")

                instance = int(fields[2])

                if not 0 <= instance < len(i2c) or i2c[instance] is not None:
                    raise RuntimeError("Invalid or duplicate I2C instance")

                i2c[instance] = {
                    "instance": instance,
                    "baudrate": int(fields[3])
                }

            elif fields[1] == "SPI":
                if len(fields) != 8:
                    raise RuntimeError("Invalid SPI configuration")

                instance = int(fields[2])

                if not 0 <= instance < len(spi) or spi[instance] is not None:
                    raise RuntimeError("Invalid or duplicate SPI instance")

                spi[instance] = {
                    "instance": instance,
                    "baudrate": int(fields[3]),
                    "data_bits": int(fields[4]),
                    "cpol": int(fields[5]),
                    "cpha": int(fields[6]),
                    "lsb_first": int(fields[7])
                }

            elif fields[1] == "UART":
                if len(fields) != 7:
                    raise RuntimeError("Invalid UART configuration")

                instance = int(fields[2])

                if not 0 <= instance < len(uart) or uart[instance] is not None:
                    raise RuntimeError("Invalid or duplicate UART instance")

                uart[instance] = {
                    "instance": instance,
                    "baudrate": int(fields[3]),
                    "data_bits": int(fields[4]),
                    "stop_bits": int(fields[5]),
                    "parity": int(fields[6])
                }

        if version is None:
            raise RuntimeError("Missing configuration version")

        if any(entry is None for entry in pins + i2c + spi + uart):
            raise RuntimeError("Incomplete configuration received")

        return {
            "config_version": version,
            "pins": pins,
            "peripherals": {
                "i2c": i2c,
                "spi": spi,
                "uart": uart
            }
        }

    def get_version(self, device_id):
        connection = self._get_connection(device_id)

        with connection["lock"]:
            device = connection["serial"]
            device.reset_input_buffer()

            self._write_line(connection, "VERSION")

            deadline = time.monotonic() + self.COMMAND_TIMEOUT

            while True:
                line = self._read_line(connection, deadline)

                if not line.startswith("VERSION,"):
                    continue

                fields = line.split(",")

                if len(fields) != 6 or fields[2] != "PROTOCOL" or fields[4] != "CONFIG":
                    raise RuntimeError("Invalid firmware version response")

                return {
                    "firmware_version": fields[1],
                    "protocol_version": int(fields[3]),
                    "config_version": int(fields[5])
                }

    def get_config(self, device_id):
        connection = self._get_connection(device_id)

        with connection["lock"]:
            device = connection["serial"]
            device.reset_input_buffer()

            self._write_line(connection, "CONFIG,GET")

            lines = []
            deadline = time.monotonic() + self.COMMAND_TIMEOUT

            while True:
                line = self._read_line(connection, deadline)

                if line == "CONFIG,END":
                    break

                lines.append(line)

            return self._parse_config(lines)

    def set_config(self, device_id, configuration):
        connection = self._get_connection(device_id)

        with connection["lock"]:
            device = connection["serial"]
            device.reset_input_buffer()

            commit_sent = False

            try:
                pins = configuration["pins"]
                peripherals = configuration["peripherals"]

                if len(pins) != 30:
                    raise ValueError("Exactly 30 GPIO entries required")

                for name in ("i2c", "spi", "uart"):
                    if len(peripherals[name]) != 2:
                        raise ValueError(
                            f"Exactly two {name.upper()} entries required"
                        )

                self._write_line(
                    connection,
                    "CONFIG,BEGIN,5"
                )
                self._wait_for(connection, "CONFIG,READY")

                for pin in pins:
                    command = (
                        f"CONFIG,PIN,{int(pin['pin'])},"
                        f"{int(pin['function'])},"
                        f"{int(pin['peripheral_instance'])},"
                        f"{int(pin['pio_priority'])},"
                        f"{int(pin['pull'])},"
                        f"{int(pin['initial_level'])},"
                        f"{int(pin['input_filter_us'])}"
                    )

                    self._write_line(connection, command)
                    self._wait_for(
                        connection,
                        f"CONFIG,PIN,OK,{int(pin['pin'])}"
                    )

                for entry in peripherals["i2c"]:
                    command = (
                        f"CONFIG,I2C,{int(entry['instance'])},"
                        f"{int(entry['baudrate'])}"
                    )

                    self._write_line(connection, command)
                    self._wait_for(
                        connection,
                        f"CONFIG,I2C,OK,{int(entry['instance'])}"
                    )

                for entry in peripherals["spi"]:
                    command = (
                        f"CONFIG,SPI,{int(entry['instance'])},"
                        f"{int(entry['baudrate'])},"
                        f"{int(entry['data_bits'])},"
                        f"{int(entry['cpol'])},"
                        f"{int(entry['cpha'])},"
                        f"{int(entry['lsb_first'])}"
                    )

                    self._write_line(connection, command)
                    self._wait_for(
                        connection,
                        f"CONFIG,SPI,OK,{int(entry['instance'])}"
                    )

                for entry in peripherals["uart"]:
                    command = (
                        f"CONFIG,UART,{int(entry['instance'])},"
                        f"{int(entry['baudrate'])},"
                        f"{int(entry['data_bits'])},"
                        f"{int(entry['stop_bits'])},"
                        f"{int(entry['parity'])}"
                    )

                    self._write_line(connection, command)
                    self._wait_for(
                        connection,
                        f"CONFIG,UART,OK,{int(entry['instance'])}"
                    )

                self._write_line(connection, "CONFIG,COMMIT")
                commit_sent = True

                deadline = time.monotonic() + self.COMMAND_TIMEOUT

                while True:
                    line = self._read_line(connection, deadline)

                    if line == "CONFIG,COMMITTED":
                        return True

            except Exception as exc:
                if commit_sent:
                    raise RuntimeError(
                        "Commit confirmation missing. "
                        "Device configuration state is unknown. "
                        "Read configuration again."
                    ) from exc

                try:
                    self._write_line(connection, "CONFIG,ABORT")
                except (serial.SerialException, OSError):
                    pass

                raise


device_communication = DeviceCommunication()
