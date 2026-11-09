"""Failure paths for the backup operator; no Docker or development data."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import mongodb_backup as backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        results = backup.ROOT / "test-results"
        results.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="backup-unit-", dir=results)
        self.directory = Path(self.temp.name).resolve()
        assert self.directory.is_relative_to(results.resolve())
        self.addCleanup(self.temp.cleanup)

    def fixture(self):
        archive = self.directory / "database.archive.gz"
        archive.write_bytes(b"archive bytes")
        manifest = {"format": 1, "snapshot": {"database": "test"},
                    "archive_sha256": backup.digest(archive)}
        (self.directory / "manifest.json").write_text(json.dumps(manifest))
        return archive

    def test_corrupt_archive_is_rejected_before_any_docker_command(self):
        self.fixture().write_bytes(b"modified")
        with patch.object(backup, "run") as run:
            with self.assertRaisesRegex(ValueError, "checksum"):
                backup.restore(["docker", "compose"], self.directory)
            run.assert_not_called()

    def test_missing_manifest_cannot_be_restored(self):
        with patch.object(backup, "run") as run:
            with self.assertRaises(FileNotFoundError):
                backup.restore([], self.directory)
            run.assert_not_called()

    def test_backup_never_overwrites_an_existing_directory(self):
        with patch.object(backup, "configuration", return_value={}):
            with self.assertRaises(FileExistsError):
                backup.backup([], self.directory)

    def test_failed_dump_restarts_only_previously_running_writers(self):
        config = {"services": {"mongodb": {"image": "mongo:8.0", "environment": {"MONGODB_DATABASE": "test"}}}}
        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, b"mongodb\napi-kms\n", b"")
        with patch.object(backup, "configuration", return_value=config), \
             patch.object(backup, "run", side_effect=fake_run) as run, \
             patch.object(backup, "snapshot", return_value={"database": "test"}), \
             patch.object(backup, "shell", side_effect=RuntimeError("dump failed")):
            destination = self.directory / "new"
            with self.assertRaisesRegex(RuntimeError, "dump failed"):
                backup.backup(["compose"], destination)
            self.assertEqual(run.call_args.args[0], ["compose", "start", "api-kms"])
            self.assertFalse((destination / "manifest.json").exists())

    def test_changed_database_is_not_certified(self):
        config = {"services": {"mongodb": {"image": "mongo:8.0", "environment": {"MONGODB_DATABASE": "test"}}}}
        with patch.object(backup, "configuration", return_value=config), \
             patch.object(backup, "run", return_value=subprocess.CompletedProcess([], 0, b"mongodb\n", b"")), \
             patch.object(backup, "snapshot", side_effect=[{"database": "test", "version": 1}, {"database": "test", "version": 2}]), \
             patch.object(backup, "shell"):
            destination = self.directory / "new"
            with self.assertRaisesRegex(RuntimeError, "changed"):
                backup.backup([], destination)
            self.assertFalse((destination / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
