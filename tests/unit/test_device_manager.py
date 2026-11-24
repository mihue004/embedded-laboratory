import sys
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host" / "testbench"))

import device_manager


class TestDeviceManager(unittest.TestCase):

    def test_discovers_multiple_devices(self):
        ports = [
            SimpleNamespace(
                device="/dev/ttyACM0",
                vid=0x2E8A,
                pid=0x0009,
                serial_number="ABC123",
                description="Pico",
                manufacturer="Raspberry Pi",
                product="Pico",
                hwid="USB VID:PID=2E8A:0009 SER=ABC123",
                location="1-1.1:1.0",
            ),
            SimpleNamespace(
                device="/dev/ttyUSB0",
                vid=0x1234,
                pid=0x5678,
                serial_number="XYZ789",
                description="Other MCU",
                manufacturer="Example",
                product="Controller",
                hwid="USB VID:PID=1234:5678 SER=XYZ789",
                location="1-1.2:1.0",
            ),
        ]

        devices = device_manager.discover_devices(
            port_provider=lambda: ports
        )

        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]["device_id"], "usb:2e8a:0009:ABC123")
        self.assertEqual(devices[1]["device_id"], "usb:1234:5678:XYZ789")
        self.assertTrue(all(device["assignable"] for device in devices))

    def test_device_id_does_not_depend_on_port_name(self):
        def create_port(device):
            return SimpleNamespace(
                device=device,
                vid=0x2E8A,
                pid=0x0009,
                serial_number="ABC123",
            )

        first = device_manager.discover_devices(
            port_provider=lambda: [create_port("/dev/ttyACM0")]
        )
        second = device_manager.discover_devices(
            port_provider=lambda: [create_port("/dev/ttyACM1")]
        )

        self.assertEqual(first[0]["device_id"], second[0]["device_id"])

    def test_device_without_serial_number_is_not_assignable(self):
        port = SimpleNamespace(
            device="/dev/ttyUSB0",
            vid=0x1234,
            pid=0x5678,
            serial_number=None,
        )

        devices = device_manager.discover_devices(
            port_provider=lambda: [port]
        )

        self.assertIsNone(devices[0]["device_id"])
        self.assertFalse(devices[0]["assignable"])

    def test_missing_optional_attributes_are_supported(self):
        port = SimpleNamespace(device="/dev/ttyUSB0")

        devices = device_manager.discover_devices(
            port_provider=lambda: [port]
        )

        self.assertEqual(len(devices), 1)
        self.assertIsNone(devices[0]["serial_number"])
        self.assertIsNone(devices[0]["description"])
        self.assertFalse(devices[0]["assignable"])

    def test_no_devices_returns_empty_list(self):
        devices = device_manager.discover_devices(
            port_provider=lambda: []
        )
        self.assertEqual(devices, [])


class TestPersistentDeviceManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "devices.json"

        self.device_a = {
            "device_id": "usb:2e8a:0009:ABC123",
            "assignable": True,
            "port": "/dev/ttyACM0",
            "manufacturer": "Raspberry Pi",
            "product": "Pico",
            "description": "Pico",
        }
        self.device_b = {
            "device_id": "usb:2e8a:0009:XYZ789",
            "assignable": True,
            "port": "/dev/ttyACM1",
            "manufacturer": "Raspberry Pi",
            "product": "Pico",
            "description": "Pico",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_new_devices_are_registered_without_roles(self):
        config = device_manager.register_devices(
            [self.device_a, self.device_b],
            self.config_path,
        )

        self.assertEqual(len(config["devices"]), 2)
        self.assertNotIn("roles", config)

    def test_device_configuration_is_persistent(self):
        device_manager.register_devices(
            [self.device_a],
            self.config_path,
        )

        loaded = device_manager.load_device_config(self.config_path)
        self.assertIn(self.device_a["device_id"], loaded["devices"])

    def test_device_settings_are_preserved(self):
        config = device_manager.register_devices(
            [self.device_a],
            self.config_path,
        )
        device_id = self.device_a["device_id"]
        config["devices"][device_id]["settings"] = {"example": True}
        device_manager.save_device_config(config, self.config_path)

        loaded = device_manager.load_device_config(self.config_path)
        self.assertEqual(
            loaded["devices"][device_id]["settings"],
            {"example": True},
        )

    def test_legacy_config_is_migrated(self):
        legacy = {
            "version": 1,
            "roles": {
                "primary": self.device_a["device_id"],
                "secondary": self.device_b["device_id"],
            },
            "devices": {
                self.device_a["device_id"]: {
                    **self.device_a,
                    "settings": {"test": 1},
                },
                self.device_b["device_id"]: {
                    **self.device_b,
                    "settings": {},
                },
            },
        }

        device_manager.save_device_config(legacy, self.config_path)
        migrated = device_manager.load_device_config(self.config_path)

        self.assertEqual(migrated["version"], 2)
        self.assertNotIn("roles", migrated)
        self.assertEqual(len(migrated["devices"]), 2)
        self.assertEqual(
            migrated["devices"][self.device_a["device_id"]]["settings"],
            {"test": 1},
        )

    def test_disconnected_device_is_retained(self):
        device_manager.register_devices(
            [self.device_a],
            self.config_path,
        )

        overview = device_manager.get_device_overview(
            discovered_devices=[],
            config_path=self.config_path,
        )

        device = overview["devices"][0]
        self.assertFalse(device["connected"])
        self.assertIsNone(device["port"])

    def test_reconnected_device_uses_current_port(self):
        device_manager.register_devices(
            [self.device_a],
            self.config_path,
        )

        reconnected = {
            **self.device_a,
            "port": "/dev/ttyACM1",
        }

        overview = device_manager.get_device_overview(
            discovered_devices=[reconnected],
            config_path=self.config_path,
        )

        self.assertTrue(overview["devices"][0]["connected"])
        self.assertEqual(overview["devices"][0]["port"], "/dev/ttyACM1")

    def test_four_devices_are_supported(self):
        devices = [
            {
                **self.device_a,
                "device_id": f"usb:2e8a:0009:DEVICE{i}",
                "serial_number": f"DEVICE{i}",
            }
            for i in range(4)
        ]

        overview = device_manager.get_device_overview(
            discovered_devices=devices,
            config_path=self.config_path,
        )

        self.assertEqual(len(overview["devices"]), 4)
        self.assertTrue(all(d["connected"] for d in overview["devices"]))


if __name__ == "__main__":
    unittest.main()
