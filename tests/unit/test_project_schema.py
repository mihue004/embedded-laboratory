import copy
import unittest
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "project.schema.yaml"
EXAMPLE_PATH = ROOT / "config" / "examples" / "pico-sdk-project.yaml"


class ProjectSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SCHEMA_PATH.open(encoding="utf-8") as stream:
            cls.schema = yaml.safe_load(stream)

        with EXAMPLE_PATH.open(encoding="utf-8") as stream:
            cls.example = yaml.safe_load(stream)

        cls.validator = jsonschema.validators.validator_for(cls.schema)(
            cls.schema
        )

    def test_example_configuration_is_valid(self):
        self.validator.validate(self.example)

    def test_missing_project_id_is_rejected(self):
        config = copy.deepcopy(self.example)
        del config["project"]["id"]

        errors = list(self.validator.iter_errors(config))

        self.assertTrue(errors)
        self.assertTrue(
            any("id" in error.message for error in errors)
        )

    def test_unknown_top_level_field_is_rejected(self):
        config = copy.deepcopy(self.example)
        config["unexpected"] = True

        errors = list(self.validator.iter_errors(config))

        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
