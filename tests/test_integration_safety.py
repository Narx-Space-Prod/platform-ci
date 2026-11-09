"""Integration tests cannot accidentally target the laptop or arbitrary images."""

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "runtime_integration", Path(__file__).resolve().parents[1] / "integration/runner.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class IntegrationSafety(unittest.TestCase):
    def test_rejects_non_ci_and_arbitrary_image_targets(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
            with self.assertRaises(ValueError):
                module.Lab("orders", "narx-check-orders:" + "a" * 40)
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            for component, image in [
                ("orders", "ghcr.io/narx-space-prod/commerce-orders:latest"),
                ("unknown", "narx-check-unknown:" + "a" * 40),
                ("cart", "narx-check-orders:" + "a" * 40),
            ]:
                with self.assertRaises(ValueError):
                    module.Lab(component, image)

    def test_setup_failure_cleans_its_own_resources(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            lab = module.Lab("frontend", "narx-check-frontend:" + "a" * 40)
        with (
            patch.object(
                lab,
                "docker",
                side_effect=["network-id", RuntimeError("fixture failed")],
            ),
            patch.object(lab, "close") as cleanup,
        ):
            with self.assertRaises(RuntimeError):
                lab.__enter__()
            cleanup.assert_called_once()

    def test_dependency_versions_are_immutable(self):
        for image in (module.POSTGRES, module.REDIS, module.PYTHON):
            self.assertRegex(image, r"@sha256:[a-f0-9]{64}$")
