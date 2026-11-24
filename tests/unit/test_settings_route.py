import sys
import tempfile
import unittest
import re
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host" / "webapp"))

import app as webapp
from settings import routes as settings_routes


class TestSettingsRoute(unittest.TestCase):

    def setUp(self):
        webapp.app.config.update(TESTING=True)
        self.client = webapp.app.test_client()

        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "devices.json"

        self.config_patch = patch.object(
            settings_routes.device_manager,
            "DEFAULT_CONFIG_PATH",
            self.config_path,
        )
        self.config_patch.start()

        self.device = {
            "device_id": "usb:2e8a:0009:ABC123",
            "assignable": True,
            "port": "/dev/ttyACM0",
            "manufacturer": "Raspberry Pi",
            "product": "Pico",
            "description": "Pico",
        }

    def csrf_headers(self):
        response = self.client.get("/settings/")
        match = re.search(
            r'<meta name="csrf-token" content="([^"]+)"',
            response.get_data(as_text=True),
        )
        self.assertIsNotNone(match)
        return {"X-CSRF-Token": match.group(1)}

    def tearDown(self):
        self.config_patch.stop()
        self.temp_dir.cleanup()

    def test_settings_page_returns_success(self):
        response = self.client.get("/settings/")
        self.assertEqual(response.status_code, 200)

    def test_all_settings_tabs_are_present(self):
        response = self.client.get("/settings/")
        content = response.get_data(as_text=True)

        self.assertIn("General", content)
        self.assertIn("Test Interface", content)
        self.assertIn("LLM Configuration", content)

    def test_back_link_points_to_main_page(self):
        response = self.client.get("/settings/")
        self.assertIn('href="/"', response.get_data(as_text=True))

    def test_settings_assets_are_available(self):
        self.assertEqual(
            self.client.get("/static/css/settings.css").status_code, 200
        )
        self.assertEqual(
            self.client.get("/static/js/settings.js").status_code, 200
        )

    def test_devices_api_returns_discovered_devices(self):
        with patch.object(
            settings_routes.device_manager,
            "discover_devices",
            return_value=[self.device],
        ):
            response = self.client.get("/settings/api/devices")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertEqual(len(data["devices"]), 1)
        self.assertEqual(
            data["devices"][0]["device_id"],
            self.device["device_id"],
        )
        self.assertTrue(data["devices"][0]["connected"])
        self.assertNotIn("roles", data)
        self.assertNotIn("role", data["devices"][0])

    def test_device_version_uses_device_id(self):
        device_id = self.device["device_id"]

        with patch.object(
            settings_routes.device_manager,
            "discover_devices",
            return_value=[self.device],
        ), patch.object(
            settings_routes.device_communication,
            "connect",
        ) as connect, patch.object(
            settings_routes.device_communication,
            "get_version",
            return_value={
                "firmware_version": "1.0",
                "protocol_version": 1,
                "config_version": 5,
            },
        ):
            response = self.client.get(
                f"/settings/api/devices/{device_id}/version"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["device_id"], device_id)
        connect.assert_called_once_with(device_id, "/dev/ttyACM0")

    def test_device_config_uses_device_id(self):
        device_id = self.device["device_id"]
        expected_config = {"config_version": 5}

        with patch.object(
            settings_routes.device_manager,
            "discover_devices",
            return_value=[self.device],
        ), patch.object(
            settings_routes.device_communication,
            "connect",
        ), patch.object(
            settings_routes.device_communication,
            "get_config",
            return_value=expected_config,
        ):
            response = self.client.get(
                f"/settings/api/devices/{device_id}/config"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["config"], expected_config)

    def test_unknown_device_is_rejected(self):
        response = self.client.get(
            "/settings/api/devices/unknown-device/version"
        )
        self.assertEqual(response.status_code, 404)

    def test_disconnected_device_is_rejected(self):
        settings_routes.device_manager.register_devices(
            [self.device],
            config_path=self.config_path,
        )

        with patch.object(
            settings_routes.device_manager,
            "discover_devices",
            return_value=[],
        ):
            response = self.client.get(
                f"/settings/api/devices/{self.device['device_id']}/version"
            )

        self.assertEqual(response.status_code, 502)

        with patch.object(
            settings_routes.device_manager,
            "discover_devices",
            return_value=[],
        ):
            response = self.client.get(
                f"/settings/api/devices/{self.device['device_id']}/version"
            )

        self.assertEqual(response.status_code, 502)

    def test_invalid_config_request_is_rejected(self):
        response = self.client.post(
            f"/settings/api/devices/{self.device['device_id']}/config",
            headers=self.csrf_headers(),
            json={"invalid": True},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
