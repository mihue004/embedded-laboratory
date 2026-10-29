import tempfile
import unittest
from pathlib import Path

from project_manager import (
    create_project,
    import_repository,
    validate_imported_project,
)


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "pico-sdk"


class ProjectManagerTests(unittest.TestCase):
    def test_create_project_from_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "my-pico-app"

            create_project(TEMPLATE, destination, "my-pico-app")

            config = destination / "project.yaml"
            self.assertTrue(config.is_file())
            self.assertTrue((destination / "CMakeLists.txt").is_file())
            self.assertTrue((destination / "src" / "main.c").is_file())
            self.assertTrue(
                (destination / "requirements" / "requirements.yaml").is_file()
            )
            self.assertEqual(validate_imported_project(destination), [])
            import yaml
            loaded = yaml.safe_load(config.read_text(encoding="utf-8"))
            self.assertEqual(loaded["project"]["id"], "my-pico-app")

    def test_invalid_project_ids_are_rejected(self):
        for project_id in ("", "-abc", "abc-", "abc--def", "Uppercase"):
            with self.subTest(project_id=project_id):
                with tempfile.TemporaryDirectory() as tmp:
                    destination = Path(tmp) / "project"
                    with self.assertRaises(ValueError):
                        create_project(TEMPLATE, destination, project_id)
                    self.assertFalse(destination.exists())

    def test_existing_destination_is_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "existing"
            destination.mkdir()
            marker = destination / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(ValueError):
                create_project(TEMPLATE, destination, "new-project")

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_import_local_repository_without_git_and_build_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "imported"
            source.mkdir()
            (source / "project.yaml").write_text(
                (TEMPLATE / "project.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (source / "main.c").write_text("int main(void) { return 0; }")
            (source / ".git").mkdir()
            (source / "build").mkdir()
            (source / ".venv").mkdir()

            import_repository(source, destination)

            self.assertTrue((destination / "main.c").is_file())
            self.assertFalse((destination / ".git").exists())
            self.assertFalse((destination / "build").exists())
            self.assertFalse((destination / ".venv").exists())
            self.assertEqual(validate_imported_project(destination), [])

    def test_import_rejects_missing_project_contract_and_cleans_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "imported"
            source.mkdir()
            (source / "README.md").write_text("No contract", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "invalid contract"):
                import_repository(source, destination)

            self.assertFalse(destination.exists())

    def test_invalid_import_does_not_modify_an_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            marker = destination / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            (source / "README.md").write_text("No contract", encoding="utf-8")

            with self.assertRaises(ValueError):
                import_repository(source, destination)

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_import_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()

            with self.assertRaises(ValueError):
                import_repository(source, destination)


if __name__ == "__main__":
    unittest.main()
