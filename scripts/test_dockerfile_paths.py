"""Unit checks for missing/misplaced Dockerfile detection; no Docker daemon."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check_dockerfiles as checker


class DockerfilePathsTest(unittest.TestCase):
    def test_finds_explicit_context_dockerfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            service = root / "frontend"
            service.mkdir()
            (service / "Dockerfile").write_text("FROM scratch\n")
            with patch.object(checker, "ROOT", root):
                builds = checker.verify_builds({
                    "services": {"frontend": {"build": {
                        "context": str(service), "dockerfile": "Dockerfile",
                    }}},
                })
            self.assertEqual(builds, [("frontend", service / "Dockerfile")])

    def test_missing_dockerfile_fails_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "frontend").mkdir()
            with patch.object(checker, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "Dockerfile missing"):
                    checker.verify_builds({"services": {
                        "frontend": {"build": {"context": str(root / "frontend"),
                                              "dockerfile": "Dockerfile"}},
                    }})

    def test_wrong_context_fails_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.object(checker, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "context directory missing"):
                    checker.verify_builds({"services": {
                        "frontend": {"build": {"context": str(root / "not-here")}},
                    }})

    def test_out_of_repo_dockerfile_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            inside = root / "repo"
            inside.mkdir()
            (root / "Dockerfile").write_text("FROM scratch")
            with patch.object(checker, "ROOT", inside):
                with self.assertRaisesRegex(ValueError, "outside DevKnowledge"):
                    checker.verify_builds({"services": {"test": {"build": {
                        "context": str(inside), "dockerfile": str(root / "Dockerfile"),
                    }}}})


    def test_real_frontend_layout_is_only_inside_ui_app(self):
        repo = Path(__file__).resolve().parents[1]
        app = repo / "frontend" / "ui-app"
        for name in ("Dockerfile", ".dockerignore", "README.md", "angular.json",
                     "package.json", "nginx.conf", "proxy.conf.json",
                     "tsconfig.json", "tsconfig.app.json", "tsconfig.spec.json"):
            self.assertTrue((app / name).is_file(), name)
            self.assertFalse((repo / "frontend" / name).exists(), name)
        for name in ("src/main.ts", "src/app/app.component.ts",
                     "src/app/components/user-admin.component.ts",
                     "src/app/services/knowledge-api.service.ts"):
            self.assertTrue((app / name).is_file(), name)
            self.assertFalse((repo / "frontend" / name).exists(), name)
        self.assertIn("context: ./frontend/ui-app",
                      (repo / "compose.yaml").read_text(encoding="utf-8"))
        self.assertIn("working-directory: frontend/ui-app",
                      (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
