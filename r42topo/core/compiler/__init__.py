"""Topology compiler: expand a validated Topology into deploy artifacts.

``compile_topology`` is the orchestrator. It validates (semantics + allocation),
resolves catalog templates, builds the artifacts in an isolated workspace, runs
the network-segmentation linter, and returns a :class:`CompileResult` of paths.
Artifacts are written under::

    <workspace>/project/topology.json
    <workspace>/project/manifest/scenario_vms.json
    <workspace>/project/network_policy.json
    <workspace>/project/stages.json
    <workspace>/inventory/hosts.yml
"""

from dataclasses import dataclass
from pathlib import Path

from r42topo.core.catalog import Catalog
from r42topo.core.compiler import inventory as _inventory
from r42topo.core.compiler import network_policy as _netpol
from r42topo.core.compiler import scenario_vms as _scenario_vms
from r42topo.core.compiler import stages as _stages
from r42topo.core.errors import CompileError
from r42topo.core.idalloc import ReservedIndex, validate_allocation
from r42topo.core.io import dump_topology
from r42topo.core.models import Topology
from r42topo.core.validate import semantic_problems


@dataclass(frozen=True)
class CompileResult:
    """Absolute paths to the artifacts produced by ``compile_topology``."""

    workspace: Path
    topology_path: Path
    inventory_path: Path
    scenario_vms_path: Path
    network_policy_path: Path
    stages_path: Path


def _write_json(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def compile_topology(
    topology: Topology,
    *,
    workspace: Path,
    catalog: Catalog,
    reserved: ReservedIndex,
) -> CompileResult:
    """Compile *topology* into deploy artifacts under *workspace*.

    :raises CompileError: on any semantic, allocation, or segmentation failure.
    """
    # 1. semantics
    problems = semantic_problems(topology, catalog)
    if problems:
        raise CompileError("topology has semantic errors: " + "; ".join(problems))

    # 2. allocation (octet rule, duplicates, cross-scenario collisions)
    report = validate_allocation(topology, reserved)
    if report.errors:
        raise CompileError("allocation errors: " + "; ".join(report.errors))

    # 3. resolve the network policy + compile its rule table
    policy = catalog.resolve_network_policy(topology.network_policy.template)
    version = catalog.resolved_version("network_policies", policy.id)
    compiled_policy = _netpol.compile_network_policy(topology, policy, version=version)

    # 4. segmentation linter — fail closed
    lint = _netpol.lint_segmentation(compiled_policy, policy, topology)
    if lint:
        raise CompileError("network segmentation linter: " + "; ".join(lint))

    # 5. build artifacts
    workspace = Path(workspace)
    project = workspace / "project"
    inv_dir = workspace / "inventory"

    topology_path = project / "topology.json"
    inventory_path = inv_dir / "hosts.yml"
    scenario_vms_path = project / "manifest" / "scenario_vms.json"
    network_policy_path = project / "network_policy.json"
    stages_path = project / "stages.json"

    dump_topology(topology, topology_path)
    _write_json(inventory_path, _inventory.build_inventory_yaml(topology))
    _write_json(scenario_vms_path, _scenario_vms.build_scenario_vms_json(topology))
    _write_json(network_policy_path, compiled_policy.model_dump_json(indent=2) + "\n")
    _write_json(stages_path, _stages.build_stages_json(topology, catalog))

    return CompileResult(
        workspace=workspace,
        topology_path=topology_path,
        inventory_path=inventory_path,
        scenario_vms_path=scenario_vms_path,
        network_policy_path=network_policy_path,
        stages_path=stages_path,
    )
