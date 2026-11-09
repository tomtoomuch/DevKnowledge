"""Guard the offline qualification against false positives; no Docker required."""
import json
import subprocess
import unittest
from unittest.mock import patch

import check_stabilization as checks


def result(value):
    return subprocess.CompletedProcess([], 0, json.dumps(value), "")


class OfflineChecksTests(unittest.TestCase):
    def test_missing_image_fails_without_download_or_resource_creation(self):
        config = {"services": {"api-kms": {"image": "missing:local"}}}
        with patch.object(checks, "run", return_value=subprocess.CompletedProcess([], 1, "", "")) as run:
            with self.assertRaisesRegex(AssertionError, "Missing local image"):
                checks.local_images(config)
            run.assert_called_once_with(["docker", "image", "inspect", "missing:local"], check=False)

    def verify_rejection(self, attachments, routes, message):
        images = {"api-kms": {"id": "sha256:test"}}
        network = [{"Internal": True, "EnableIPv6": False}]
        container = [{"Image": "sha256:test", "NetworkSettings": {"Networks": attachments}}]
        with patch.object(checks, "run", side_effect=[result(network), result(container)]), \
             patch.object(checks, "compose", side_effect=[subprocess.CompletedProcess([], 0, "container", ""),
                                                          subprocess.CompletedProcess([], 0, routes, "")]), \
             patch.object(checks, "kms_python") as probe:
            with self.assertRaisesRegex(AssertionError, message):
                checks.verify_offline_network(images)
            probe.assert_not_called()

    def test_extra_network_attachment_is_rejected(self):
        self.verify_rejection({checks.PROJECT + "_default": {}, "outside": {}}, "", "attachment")

    def test_default_route_is_rejected_even_on_declared_internal_network(self):
        self.verify_rejection({checks.PROJECT + "_default": {}},
                              "Iface Destination Gateway\neth0 00000000 010011AC\n", "default route")


if __name__ == "__main__":
    unittest.main()
