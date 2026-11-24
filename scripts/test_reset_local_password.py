"""Check hidden password entry and transport without touching application data."""
import contextlib
import getpass
import io
import json
import subprocess
import unittest
from unittest.mock import patch

import reset_local_password as reset


class ResetPasswordTests(unittest.TestCase):
    def test_password_only_travels_on_stdin(self):
        password = "Temporary-test-password-42"
        output = io.StringIO()
        with patch("sys.argv", ["reset", "--username", "admin"]), \
             patch.object(reset.getpass, "getpass", side_effect=[password, password]), \
             patch.object(reset.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
             contextlib.redirect_stdout(output):
            reset.main()
        self.assertNotIn(password, repr(run.call_args.args[0]))
        self.assertEqual(json.loads(run.call_args.kwargs["input"]), {"username": "admin", "password": password})
        self.assertNotIn(password, output.getvalue())

    def test_mismatch_or_invalid_password_does_not_start_docker(self):
        for values in [("first-password", "second-password"), ("short", "short")]:
            with self.subTest(values=values), patch("sys.argv", ["reset"]), \
                 patch.object(reset.getpass, "getpass", side_effect=values), \
                 patch.object(reset.subprocess, "run") as run:
                with self.assertRaises(SystemExit):
                    reset.main()
                run.assert_not_called()

    def test_visible_input_fallback_is_refused(self):
        with patch("sys.argv", ["reset"]), \
             patch.object(reset.getpass, "getpass", side_effect=getpass.GetPassWarning()), \
             patch.object(reset.subprocess, "run") as run:
            with self.assertRaisesRegex(SystemExit, "terminal interactif"):
                reset.main()
            run.assert_not_called()

    def test_failed_docker_output_is_not_exposed(self):
        password = "Temporary-test-password-42"
        with patch("sys.argv", ["reset"]), \
             patch.object(reset.getpass, "getpass", side_effect=[password, password]), \
             patch.object(reset.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, password, password)):
            with self.assertRaises(SystemExit) as caught:
                reset.main()
        self.assertNotIn(password, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
