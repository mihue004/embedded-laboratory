import copy
import unittest
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "device-profile.schema.yaml"
PROFILE_PATH = ROOT / "config" / "devices" / "pico2.yaml"


class DeviceProfileSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SCHEMA_PATH.open(encoding="utf-8") as stream:
            cls.schema = yaml.safe_load(stream)

        with PROFILE_PATH.open(encoding="utf-8") as stream:
            cls.profile = yaml.safe_load(stream)

        validator_class = jsonschema.validators.validator_for(cls.schema)
        validator_class.check_schema(cls.schema)
        cls.validator = validator_class(cls.schema)

    def test_pico2_profile_is_valid(self):
        self.validator.validate(self.profile)

    def test_missing_device_class_is_rejected(self):
        profile = copy.deepcopy(self.profile)
        del profile["device_class"]
        self.assertTrue(list(self.validator.iter_errors(profile)))

    def test_unknown_capability_status_is_rejected(self):
        profile = copy.deepcopy(self.profile)
        profile["capabilities"][0]["status"] = "available"
        self.assertTrue(list(self.validator.iter_errors(profile)))

    def test_unknown_top_level_field_is_rejected(self):
        profile = copy.deepcopy(self.profile)
        profile["permanent_role"] = "generator"
        self.assertTrue(list(self.validator.iter_errors(profile)))


if __name__ == "__main__":
    unittest.main()
