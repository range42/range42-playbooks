"""General catalog preparation uses the shared native attempt entrypoint."""
import json
from pathlib import Path
from test_native_workshop_foundation import test_real_ansible_hands_the_private_request_to_the_fixed_backend_adapter as check_native
import test_native_workshop_foundation as legacy

ROOT=Path(__file__).resolve().parents[1]
SCENARIO=ROOT/'scenarios/template_preparation'


def test_general_recipe_has_no_workshop_or_provider_specific_inputs():
    assert (SCENARIO/'manifest/preparation.json').is_file()
    data=json.loads((SCENARIO/'manifest/preparation.json').read_text())
    assert data=={'version':1,'kind':'native-template-preparation','title':'Prepare reusable templates'}
    assert json.loads((SCENARIO/'manifest/scenario_vms.json').read_text())['vms']==[]
    assert 'headscale' not in (SCENARIO/'main.yml').read_text().lower()


def test_generic_recipe_uses_the_same_private_native_adapter(tmp_path,monkeypatch):
    monkeypatch.setattr(legacy,'SCENARIO',SCENARIO)
    check_native(tmp_path)
