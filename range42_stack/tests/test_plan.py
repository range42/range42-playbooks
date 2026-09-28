import copy
import importlib
import ipaddress
import json
import unittest
from pathlib import Path


def spec(name="alpha", base=31000, subnet="10.81.0.0/24", bridge="r42alpha"):
    return {
        "id": name, "domain": f"{name}.example.test", "vmid_start": base,
        "subnet": subnet, "gateway": str(ipaddress.ip_network(subnet)[1]),
        "bridge": bridge, "template_vmid": 9221, "node": "pve", "ssh_user": "alice",
        "profile": "full",
    }


class StackPlanTests(unittest.TestCase):
    def implementation(self):
        path = Path(__file__).parents[1] / "plan.py"
        self.assertTrue(path.exists(), "isolated stack planner is missing")
        return importlib.import_module("range42_stack.plan")

    def test_full_stack_has_all_deployable_tools_and_preview_is_explicit(self):
        plan = self.implementation().build_plan(spec())
        self.assertEqual({vm["service"] for vm in plan["vms"]}, {
            "gateway", "backend", "ui", "cli", "reporting", "wazuh",
            "gitea", "registry", "mattermost", "rocketchat", "nextcloud",
        })
        self.assertEqual(plan["unavailable"]["emp"], "preview")
        self.assertIn("misp", plan["unavailable"])

    def test_two_instances_have_disjoint_resources_and_own_urls(self):
        planner = self.implementation()
        a = planner.build_plan(spec())
        b = planner.build_plan(spec("bravo", 32000, "10.82.0.0/24", "r42bravo"), peers=[a])
        for field in ("vm_id", "vm_name", "ip", "project_name", "install_root"):
            self.assertFalse({v[field] for v in a["vms"]} & {v[field] for v in b["vms"]}, field)
        self.assertEqual(a["endpoints"]["backend"], "https://api.alpha.example.test")
        self.assertEqual(b["endpoints"]["reporting"], "https://reporting.bravo.example.test")
        self.assertEqual(len(a["vms"]), len({v["vm_id"] for v in a["vms"]}))

    def test_rejects_colliding_names_vmids_networks_and_domains(self):
        planner = self.implementation()
        a = planner.build_plan(spec())
        b = spec("bravo", 32000, "10.82.0.0/24", "r42bravo")
        for field, value in [("id", "alpha"), ("vmid_start", 31001), ("subnet", "10.81.0.0/25"),
                             ("bridge", "r42alpha"), ("domain", "alpha.example.test")]:
            candidate = dict(b, **{field: value})
            if field == "subnet":
                candidate["gateway"] = "10.81.0.1"
            with self.subTest(field=field), self.assertRaises(ValueError):
                planner.build_plan(candidate, peers=[a])

    def test_rejects_unsafe_or_unusable_allocations(self):
        planner = self.implementation()
        for field, value in [("id", "../alpha"), ("vmid_start", 100), ("vmid_start", True),
                             ("template_vmid", 31000), ("domain", "evil/path"),
                             ("subnet", "10.81.0.0/29"), ("gateway", "10.99.0.1"),
                             ("bridge", "vmbr0"), ("bridge", "vmbr142"), ("ssh_user", "root;echo")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                planner.build_plan(dict(spec(), **{field: value}))

    def test_storage_override_is_rejected_instead_of_silently_ignored(self):
        with self.assertRaises(ValueError):
            self.implementation().build_plan(dict(spec(), storage='other-storage'))

    def test_core_profile_and_reproducible_plan_do_not_embed_credentials(self):
        planner = self.implementation()
        source = dict(spec(), profile="core")
        before = copy.deepcopy(source)
        a = planner.build_plan(source)
        self.assertEqual(a, planner.build_plan(source))
        self.assertEqual(source, before)
        self.assertEqual(len(a["vms"]), 5)
        self.assertNotIn("token", json.dumps(a))
        self.assertEqual(a["dns"], "1.1.1.1")

    def test_loopback_is_not_a_usable_private_stack_network(self):
        with self.assertRaises(ValueError):
            self.implementation().build_plan(dict(spec(), subnet="127.0.0.0/24", gateway="127.0.0.1"))

    def test_cluster_vmids_and_sdn_names_cannot_collide_across_nodes(self):
        planner = self.implementation()
        a = planner.build_plan(spec())
        for overrides in ({"vmid_start": 31000}, {"bridge": "r42alpha"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                planner.build_plan(dict(spec("bravo", 32000, "10.82.0.0/24", "r42bravo"),
                                        node="other", **overrides), peers=[a])


if __name__ == "__main__":
    unittest.main()
