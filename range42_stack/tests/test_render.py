import importlib
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from range42_stack.plan import build_plan
from test_plan import spec


class RenderTests(unittest.TestCase):
    def renderer(self):
        self.assertTrue((Path(__file__).parents[1] / "render.py").exists(), "stack renderer is missing")
        return importlib.import_module("range42_stack.render")

    def test_gateway_routes_all_services_and_keeps_backend_bearer_auth(self):
        plan = build_plan(spec())
        config = self.renderer().kong_config(plan)
        routes = {s["name"]: s for s in config["services"]}
        self.assertEqual(set(routes), set(plan["endpoints"]))
        self.assertEqual(routes["backend"]["routes"][0]["hosts"], ["api.alpha.example.test"])
        self.assertFalse(routes["backend"]["routes"][0]["strip_path"])
        self.assertEqual(routes["backend"]["url"], "http://10.81.0.11:8000")
        self.assertNotIn("plugins", config)  # no shared credential injected at the gateway

    def test_catalog_payload_loses_global_names_and_sample_users(self):
        renderer = self.renderer()
        source = {"services": {"gitea": {"image": "gitea/gitea:1.24", "container_name": "gitea",
                   "ports": ["${HTTP_PORT:-3000}:3000"], "volumes": ["data:/data"]}},
                  "volumes": {"data": {"name": "global-data"}}}
        normalized = renderer.catalog_compose(build_plan(spec()), "gitea", source)
        self.assertNotIn("container_name", normalized["services"]["gitea"])
        self.assertNotIn("name", normalized["volumes"]["data"])
        self.assertEqual(normalized["services"]["gitea"]["ports"], ["10.81.0.16:${HTTP_PORT:-3000}:3000"])
        self.assertIn("container_name", source["services"]["gitea"])
        for unsafe in ({"external": True}, {"driver_opts": {"device": "/parent/state"}}):
            source["volumes"]["data"] = unsafe
            with self.assertRaises(ValueError):
                renderer.catalog_compose(build_plan(spec()), "gitea", source)

    def test_credentials_are_distinct_persistent_and_private(self):
        renderer = self.renderer()
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a", Path(temp) / "b"
            first = renderer.ensure_credentials(a, "alpha", "backend")
            self.assertEqual(first, renderer.ensure_credentials(a, "alpha", "backend"))
            self.assertNotEqual(first, renderer.ensure_credentials(b, "bravo", "backend"))
            self.assertEqual((a / "api-token").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                renderer.ensure_credentials(a, "bravo", "backend")
            (a / "credential-key").unlink()
            with self.assertRaises(ValueError):
                renderer.ensure_credentials(a, "alpha", "backend")



if __name__ == "__main__":
    unittest.main()
