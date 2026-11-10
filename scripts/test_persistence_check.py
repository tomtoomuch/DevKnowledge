"""The volume auditor cannot mutate Docker resources."""
import json
import unittest
from unittest.mock import patch

from persistence_check import PersistenceError, inspect


CONFIG = {
    "name": "myproject", "services": {"mongodb": {"volumes": [
        {"type": "volume", "source": "mongodb", "target": "/data/db"},
        {"type": "volume", "source": "mongodb-configdb", "target": "/data/configdb"},
    ]}},
    "volumes": {
        "mongodb": {"name": "myproject_mongodb"},
        "mongodb-configdb": {"name": "myproject_mongodb-configdb"},
    },
}


class PersistenceAuditTests(unittest.TestCase):
    @patch("persistence_check.docker")
    def test_matches_project_scoped_volumes(self, runner):
        runner.side_effect = [
            json.dumps(CONFIG), "container-id", "myproject_mongodb\nother_mongodb",
            json.dumps([{"Mounts": [
                {"Type": "volume", "Destination": "/data/db", "Name": "myproject_mongodb"},
                {"Type": "volume", "Destination": "/data/configdb", "Name": "myproject_mongodb-configdb"},
            ]}]),
        ]
        report = inspect(project="myproject", env_file=".env")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["other_compose_mongodb_volumes"], ["other_mongodb"])
        commands = runner.call_args_list
        self.assertTrue(all("down" not in repr(call) and "up" not in repr(call)
                            and "volume rm" not in repr(call) for call in commands))

    @patch("persistence_check.docker")
    def test_detects_wrong_mount_without_touching_it(self, runner):
        runner.side_effect = [
            json.dumps(CONFIG), "container-id", "other_mongodb",
            json.dumps([{"Mounts": [
                {"Type": "volume", "Destination": "/data/db", "Name": "other_mongodb"},
            ]}]),
        ]
        self.assertEqual(inspect()["status"], "mismatch")

    @patch("persistence_check.docker")
    def test_missing_container_does_not_create_volumes(self, runner):
        runner.side_effect = [json.dumps(CONFIG), "", "orphaned_mongodb"]
        result = inspect()
        self.assertEqual(result["status"], "not_running")
        self.assertEqual(result["other_compose_mongodb_volumes"], ["orphaned_mongodb"])
        self.assertEqual(runner.call_count, 3)

    @patch("persistence_check.docker")
    def test_requires_named_data_and_config_mounts(self, runner):
        broken = json.loads(json.dumps(CONFIG))
        broken["services"]["mongodb"]["volumes"][0]["type"] = "bind"
        runner.return_value = json.dumps(broken)
        with self.assertRaises(PersistenceError):
            inspect()
