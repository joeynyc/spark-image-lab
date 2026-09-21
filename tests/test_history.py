import json
from pathlib import Path
import tempfile
import unittest

from history import (delete_generation, load_history, restore_generation,
                     save_generation, validate_request)


class FakeImage:
    def save(self, path, **kwargs):
        Path(path).write_bytes(b"test-image")


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "outputs"
        self.metadata = dict(prompt="A miniature city", width=1024, height=1024,
                             steps=40, seed=42, elapsed_seconds=52.5,
                             peak_allocated_gib=36.9)

    def save(self, refs=()):
        return save_generation(self.root, FakeImage(), self.metadata, refs)

    def test_round_trip_and_persistent_references(self):
        reference = Path(self.temp.name) / "original.png"
        reference.write_bytes(b"reference-image")
        image, record, metadata = self.save([reference])
        reference.unlink()
        entries = load_history(self.root)
        self.assertEqual(len(entries), 1)
        restored = restore_generation(self.root, entries[0]["id"])
        self.assertEqual(restored["prompt"], self.metadata["prompt"])
        self.assertEqual(restored["seed"], 42)
        self.assertEqual(Path(restored["reference_paths"][0]).read_bytes(), b"reference-image")
        self.assertEqual(restored["image_path"], image)
        self.assertTrue(Path(record).is_file())
        self.assertEqual(metadata["schema_version"], 1)

    def test_newest_first_and_no_duplicates(self):
        first = self.save()[2]["id"]
        second = self.save()[2]["id"]
        self.assertEqual([r["id"] for r in load_history(self.root)], [second, first])

    def test_empty_and_malformed_history(self):
        self.assertEqual(load_history(self.root), [])
        self.save()
        (self.root / "broken.json").write_text("{broken")
        (self.root / "broken.png").write_bytes(b"image")
        (self.root / "demo-manifest.json").write_text('{"demo": "somewhere.png"}')
        self.assertEqual(len(load_history(self.root)), 1)

    def test_legacy_record_is_read_without_modification(self):
        self.root.mkdir()
        legacy = dict(self.metadata, references=[{"filename": "lost.png", "sha256": "123"}])
        path = self.root / "20260920-120000-old.json"
        original = json.dumps(legacy)
        path.write_text(original)
        path.with_suffix(".png").write_bytes(b"old")
        entry = restore_generation(self.root, load_history(self.root)[0]["id"])
        self.assertEqual(entry["missing_references"], 1)
        self.assertEqual(entry["reference_paths"], [])
        self.assertEqual(path.read_text(), original)

    def test_missing_image_is_not_listed(self):
        image, _, _ = self.save()
        Path(image).unlink()
        self.assertEqual(load_history(self.root), [])

    def test_reference_path_cannot_escape_output_directory(self):
        _, record, _ = self.save()
        data = json.loads(Path(record).read_text())
        data["references"] = [{"path": "../secret.png"}]
        Path(record).write_text(json.dumps(data))
        entry = restore_generation(self.root, data["id"])
        self.assertEqual(entry["missing_references"], 1)
        self.assertEqual(entry["reference_paths"], [])
        with self.assertRaises(ValueError):
            restore_generation(self.root, "../secret")

    def test_failed_save_is_not_visible(self):
        class BrokenImage:
            def save(self, path, **kwargs):
                raise OSError("disk full")
        with self.assertRaises(OSError):
            save_generation(self.root, BrokenImage(), self.metadata, [])
        self.assertEqual(load_history(self.root), [])

    def test_failed_metadata_save_removes_new_reference_copy(self):
        reference = Path(self.temp.name) / "ref.png"
        reference.write_bytes(b"private")
        metadata = dict(self.metadata, elapsed_seconds=float("nan"))
        with self.assertRaises(ValueError):
            save_generation(self.root, FakeImage(), metadata, [reference])
        self.assertEqual(list((self.root / "references").iterdir()), [])

    def test_missing_saved_reference_is_reported(self):
        reference = Path(self.temp.name) / "ref.png"
        reference.write_bytes(b"ref")
        _, _, saved = self.save([reference])
        (self.root / saved["references"][0]["path"]).unlink()
        self.assertEqual(restore_generation(self.root, saved["id"])["missing_references"], 1)

    def test_symlink_reference_cannot_escape_output_directory(self):
        _, record, saved = self.save()
        outside = Path(self.temp.name) / "secret.png"
        outside.write_bytes(b"private")
        (self.root / "linked.png").symlink_to(outside)
        saved["references"] = [{"path": "linked.png"}]
        Path(record).write_text(json.dumps(saved))
        restored = restore_generation(self.root, saved["id"])
        self.assertEqual(restored["reference_paths"], [])
        self.assertEqual(restored["missing_references"], 1)

    def test_reference_storage_symlink_cannot_escape_output_directory(self):
        self.root.mkdir()
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "references").symlink_to(outside, target_is_directory=True)
        reference = Path(self.temp.name) / "ref.png"
        reference.write_bytes(b"private")
        with self.assertRaises(ValueError):
            self.save([reference])
        self.assertEqual(list(outside.iterdir()), [])

    def test_repeated_reference_is_deduplicated(self):
        reference = Path(self.temp.name) / "ref.png"
        reference.write_bytes(b"same reference")
        self.save([reference])
        self.save([reference])
        self.assertEqual(len(list((self.root / "references").iterdir())), 1)

    def test_delete_generation_removes_image_record_and_orphaned_reference(self):
        reference = Path(self.temp.name) / "ref.png"
        reference.write_bytes(b"private reference")
        image, record, saved = self.save([reference])
        stored_reference = self.root / saved["references"][0]["path"]

        delete_generation(self.root, saved["id"])

        self.assertFalse(Path(image).exists())
        self.assertFalse(Path(record).exists())
        self.assertFalse(stored_reference.exists())
        self.assertEqual(load_history(self.root), [])

    def test_delete_generation_keeps_shared_reference_until_last_use(self):
        reference = Path(self.temp.name) / "ref.png"
        reference.write_bytes(b"shared reference")
        first = self.save([reference])[2]
        second = self.save([reference])[2]
        stored_reference = self.root / first["references"][0]["path"]

        delete_generation(self.root, first["id"])
        self.assertTrue(stored_reference.is_file())

        delete_generation(self.root, second["id"])
        self.assertFalse(stored_reference.exists())

    def test_delete_generation_rejects_invalid_or_missing_entry(self):
        image, record, _ = self.save()
        for identifier in ("../secret", "missing"):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                delete_generation(self.root, identifier)
        self.assertTrue(Path(image).is_file())
        self.assertTrue(Path(record).is_file())

    def test_invalid_reference_metadata_is_skipped(self):
        _, record, saved = self.save()
        saved["references"] = [{"filename": 123}]
        Path(record).write_text(json.dumps(saved))
        self.assertEqual(load_history(self.root), [])


class ValidationTests(unittest.TestCase):
    def test_valid_request(self):
        self.assertEqual(validate_request("  city  ", 1024, 1024, 40, 42),
                         ("city", 1024, 1024, 40, 42))

    def test_invalid_values(self):
        for field, value in [(0, " "), (1, 511), (1, 1025), (2, 2784),
                             (3, 0), (3, 81), (4, -1), (4, 2**32),
                             (1, 1024.5), (4, float("nan")), (4, True), (4, 2**2000)]:
            values = ["city", 1024, 1024, 40, 42]
            values[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_request(*values)


if __name__ == "__main__":
    unittest.main()
