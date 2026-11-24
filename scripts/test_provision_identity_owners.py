"""Provisioning must not write grants before backup and restore gates pass."""
import subprocess
import unittest
from unittest.mock import patch

import provision_identity_owners as provision


class ProvisionTests(unittest.TestCase):
    def test_backup_database_mismatch_stops_before_any_container_mutation(self):
        with patch("sys.argv", ["provision", "--project", "isolated", "--env-file", "unused", "--backup", "unused"]), \
             patch.object(provision, "configuration", return_value={"services": {"mongodb": {"environment": {"MONGODB_DATABASE": "expected"}}}}), \
             patch.object(provision, "read_backup", return_value=(None, {"snapshot": {"database": "other"}})), \
             patch.object(provision, "run") as run:
            with self.assertRaisesRegex(SystemExit, "does not match"):
                provision.main()
            run.assert_not_called()

    def test_changed_source_stays_stopped_without_provisioning_or_restore(self):
        with patch("sys.argv", ["provision", "--project", "isolated", "--env-file", "unused", "--backup", "unused"]), \
             patch.object(provision, "configuration", return_value={"services": {"mongodb": {"environment": {"MONGODB_DATABASE": "expected"}}}}), \
             patch.object(provision, "read_backup", return_value=(None, {"snapshot": {"database": "expected", "collections": ["backup"]}})), \
             patch.object(provision, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.object(provision, "snapshot", return_value={"collections": ["changed"]}), \
             patch.object(provision, "restore") as restore, patch.object(provision, "shell") as shell:
            with self.assertRaisesRegex(SystemExit, "Source changed"):
                provision.main()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][-4:], ["stop", "api-gateway", "api-kms", "supervisor"])
            restore.assert_not_called()
            shell.assert_not_called()


if __name__ == "__main__":
    unittest.main()
