import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scenarios" / "misp_lab" / "manifest" / "world.json"


class MispLabWorldManifestTests(unittest.TestCase):
    def test_misp_lab_binds_both_training_storylines_to_nacre_uuids(self) -> None:
        self.assertTrue(MANIFEST.is_file(), "misp_lab is missing manifest/world.json")

        with MANIFEST.open() as handle:
            document = json.load(handle)

        self.assertEqual("1.0", document["schema_version"])
        self.assertEqual(
            {
                "id": "nacre",
                "format": "misp-galaxy",
                "galaxy_type": "exercise-world",
                "galaxy_uuid": "3c3de5f0-5982-4c7f-88cf-8abf43b8d6c1",
                "collection_uuid": "7d6d7f2f-b3d4-4bc5-9f27-43e12f7f4658",
                "version": 1,
                "cluster_commit": "cc7792ad2406700bcdd0462927c9fd0f5ddee84a",
                "cluster_sha256": "55afe65a817c167a46dbd26850515aefb2bf72b9318f651d6adb172e498a44b4",
            },
            document["world"],
        )

        expected = {
            "c0ffee01-cafe-4bab-b000-000000000001": {
                "country": ("cb97ba71-e477-4acb-9470-10f3e6c9e1a9", "Asterin Union"),
                "victim_company": ("e3d6ab68-ad7b-4deb-9c0d-c0250013d1bb", "NovaCore Systems"),
                "threat_actor": ("6c922d71-43e3-40c4-a1ea-85929f0c2f1a", "TA-700 Obsidian Jackal"),
            },
            "c0ffee02-cafe-4bab-b000-000000000002": {
                "country": ("e4cd09cc-7be7-46ef-8989-5b9a812b49fe", "Velkar Republic"),
                "victim_company": ("df601e63-1a5f-4cec-a071-152f1c62f310", "HelixCore Group"),
                "threat_actor": ("e8b1ce9a-128c-4546-907d-02178fc72e49", "TA-701 Silver Mantis"),
            },
        }
        actual = {
            storyline["misp_event_uuid"]: {
                role: (entity["uuid"], entity["value"])
                for role, entity in storyline["entities"].items()
            }
            for storyline in document["storylines"]
        }
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
