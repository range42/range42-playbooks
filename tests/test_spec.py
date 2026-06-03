"""Step 2 — scenario.r42.yml composition spec tests (RED before GREEN).

Covers: valid spec round-trips through YAML; unknown/bad fields are rejected
(extra="forbid"); deny-listed free-text (injection) is rejected; IO error paths.
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from r42playbooks.core.errors import TopologyError
from r42playbooks.core.spec import ScenarioSpec, dump_spec_atomic, load_spec


def test_valid_spec_round_trips(tmp_path, valid_spec_dict):
    # Arrange
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    path = tmp_path / "scenario.r42.yml"

    # Act
    dump_spec_atomic(spec, path)
    loaded = load_spec(path)

    # Assert
    assert loaded == spec


def test_dump_is_deterministic(tmp_path, valid_spec_dict):
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    p1, p2 = tmp_path / "a.yml", tmp_path / "b.yml"
    dump_spec_atomic(spec, p1)
    dump_spec_atomic(spec, p2)
    assert p1.read_text() == p2.read_text()  # byte-identical


def test_count_defaults_to_one(valid_spec_dict):
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    assert spec.boxes[0].count == 1  # admin-wazuh has no explicit count


def test_optional_fields_may_be_omitted(spec_factory):
    data = spec_factory()
    del data["proxmox_node"]
    del data["notes"]
    spec = ScenarioSpec.model_validate(data)
    assert spec.proxmox_node is None
    assert spec.notes == ""


def test_unknown_top_level_field_rejected(spec_factory):
    data = spec_factory(unexpected="boom")
    with pytest.raises(PydanticValidationError):
        ScenarioSpec.model_validate(data)


def test_unknown_box_field_rejected(valid_spec_dict):
    valid_spec_dict["boxes"][0]["junk"] = 1
    with pytest.raises(PydanticValidationError):
        ScenarioSpec.model_validate(valid_spec_dict)


def test_bad_name_rejected(spec_factory):
    data = spec_factory(name="has spaces")
    with pytest.raises(PydanticValidationError):
        ScenarioSpec.model_validate(data)


def test_empty_boxes_rejected(spec_factory):
    data = spec_factory(boxes=[])
    with pytest.raises(PydanticValidationError):
        ScenarioSpec.model_validate(data)


def test_injection_in_notes_rejected(spec_factory):
    data = spec_factory(notes="{{ malicious }}")
    with pytest.raises(PydanticValidationError):
        ScenarioSpec.model_validate(data)


def test_injection_in_box_vars_rejected(valid_spec_dict):
    valid_spec_dict["boxes"][0]["vars"] = {"x": "${SECRET}"}
    with pytest.raises(PydanticValidationError):
        ScenarioSpec.model_validate(valid_spec_dict)


def test_count_must_be_positive(valid_spec_dict):
    valid_spec_dict["boxes"][0]["count"] = 0
    with pytest.raises(PydanticValidationError):
        ScenarioSpec.model_validate(valid_spec_dict)


def test_template_vm_id_override_accepted(valid_spec_dict):
    # §7.1 resolved decision: a box may pin its template via template_vm_id.
    valid_spec_dict["boxes"][0]["template_vm_id"] = 9234
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    assert spec.boxes[0].template_vm_id == 9234


def test_load_spec_rejects_missing_file(tmp_path):
    with pytest.raises(TopologyError):
        load_spec(tmp_path / "nope.r42.yml")


def test_load_spec_rejects_invalid_yaml(tmp_path):
    bad = tmp_path / "bad.r42.yml"
    bad.write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(TopologyError):
        load_spec(bad)


def test_load_spec_rejects_schema_violation(tmp_path):
    bad = tmp_path / "bad.r42.yml"
    bad.write_text("name: my_lab\n", encoding="utf-8")  # missing required fields
    with pytest.raises(TopologyError):
        load_spec(bad)
