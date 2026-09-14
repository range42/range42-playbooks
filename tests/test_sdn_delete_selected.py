"""Actual selected-VNet composite preserves same-zone neighbours and dry runs."""

import json
from pathlib import Path

import pytest

from test_sdn_delete_all import paired, repeat


def test_selected_delete_keeps_shared_zone_and_other_vnet_attachments(
    tmp_path, monkeypatch
):
    result, observed, fixture = paired(tmp_path, monkeypatch, selected=True)
    assert result.returncode == 0, result.stdout[-9000:] + result.stderr
    assert json.loads((tmp_path / "deletions.json").read_text()) == [
        "/api2/json/cluster/sdn/vnets/net1/subnets/lab-10.42.70.0-24",
        "/api2/json/cluster/sdn/vnets/net1",
    ]
    assert json.loads(Path(observed["nodes"]["pve1"]["state"]).read_text()) == [
        fixture.UNRELATED,
        fixture.OTHER_RULE,
    ]
    assert (
        json.loads(Path(observed["nodes"]["pve2"]["state"]).read_text())
        == [fixture.UNRELATED, fixture.OTHER_RULE] + [fixture.TARGET_RULE] * 2
    )
    journal_path = tmp_path / "config/.sdn-delete/lab.json"
    journal = json.loads(journal_path.read_text())
    assert journal["state"] == "completed"
    assert journal["payload"]["scope"]["selection"] == "vnets"
    assert journal["payload"]["scope"]["requested_vnets"] == ["net1"]
    before = journal_path.read_bytes()
    (tmp_path / "scope.json").write_bytes((tmp_path / "after.json").read_bytes())
    again = repeat(tmp_path)
    assert again.returncode == 0, again.stdout[-6000:] + again.stderr
    assert journal_path.read_bytes() == before
    assert len(json.loads((tmp_path / "deletions.json").read_text())) == 2


def test_selected_read_only_has_no_declaration_rule_apply_or_journal_writes(
    tmp_path, monkeypatch
):
    result, observed, _ = paired(tmp_path, monkeypatch, selected=True, read_only=True)
    assert result.returncode == 0, result.stdout[-9000:] + result.stderr
    assert not (tmp_path / "deletions.json").exists()
    assert not Path(observed["apply_marker"]).exists()
    assert not (tmp_path / "config/.sdn-delete").exists()
    assert all(
        json.loads(Path(node["writes"]).read_text()) == []
        for node in observed["nodes"].values()
    )
    assert "read-only" in result.stdout.lower()


@pytest.mark.parametrize(
    "fault", ["missing_cidr", "pending", "attached", "offline", "wrong_host", "drift"]
)
def test_selected_delete_refuses_before_write(tmp_path, monkeypatch, fault):
    options = {fault: True} if fault in ("offline", "wrong_host") else {}
    result, observed, _ = paired(
        tmp_path, monkeypatch, selected=True, fault=fault, **options
    )
    assert result.returncode != 0
    assert not (tmp_path / "deletions.json").exists()
    assert not Path(observed["apply_marker"]).exists()


def test_selected_partial_delete_retains_intent_and_blocks_other_selection(
    tmp_path, monkeypatch
):
    result, observed, _ = paired(tmp_path, monkeypatch, selected=True, fault="partial")
    assert result.returncode != 0
    journal_path = tmp_path / "config/.sdn-delete/lab.json"
    before = journal_path.read_bytes()
    journal = json.loads(before)
    assert journal["state"] == "incomplete"
    assert journal["payload"]["scope"]["requested_vnets"] == ["net1"]
    play = tmp_path / "playbook.yml"
    play.write_text(play.read_text().replace("- net1", "- outside"))
    assert repeat(tmp_path).returncode != 0
    assert journal_path.read_bytes() == before
    assert not Path(observed["apply_marker"]).exists()
