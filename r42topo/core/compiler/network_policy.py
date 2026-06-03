"""Compile a symbolic network policy + topology bindings into ordered FORWARD rules.

iptables FORWARD is first-match-wins, so rule ORDER is correctness, not style.
Each emitted rule gets a deterministic ``weight`` from a fixed band table; the
final list is stable-sorted by (weight, source, destination, proto, port, jump)
so identical inputs yield byte-identical output. The deploy playbook (Plan B)
flush-rebuilds a dedicated ``R42-FORWARD`` chain from this list in order, which
is naturally idempotent and never touches the host INPUT chain (SSH stays up).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from r42topo.core.catalog_models import MatrixRule, NetworkPolicyTemplate, PortSpec
from r42topo.core.models import Topology
from r42topo.core.validate import zone_bridge_map, zone_subnet_map

# weight bands — lower weight is evaluated earlier in FORWARD
W_ESTABLISHED = 0
W_SERVICE_ACCEPT = 100
W_ZONE_ACCEPT = 200
W_INTRA = 300
W_ZONE_DROP = 500
W_AIRGAP = 600
W_DEFAULT = 900

_ACTION_JUMP = {"accept": "ACCEPT", "drop": "DROP", "reject": "REJECT"}
_SVC = "svc:"


class CompiledRule(BaseModel):
    """A single iptables FORWARD rule, fully resolved to concrete values."""

    model_config = ConfigDict(extra="forbid")

    weight: int
    chain: Literal["FORWARD"] = "FORWARD"
    proto: Literal["tcp", "udp", "icmp", "all"] = "all"
    source: str | None = None
    destination: str | None = None
    destination_port: str | None = None
    in_interface: str | None = None
    out_interface: str | None = None
    ctstate: str | None = None
    jump: Literal["ACCEPT", "DROP", "REJECT"]
    comment: str


class CompiledNetworkPolicy(BaseModel):
    """The ordered FORWARD rule table produced from a policy + topology."""

    model_config = ConfigDict(extra="forbid")

    chain: Literal["FORWARD"] = "FORWARD"
    policy_id: str
    policy_version: str
    wan_interface: str
    rules: list[CompiledRule] = Field(default_factory=list)


def _sort_key(r: CompiledRule) -> tuple:
    return (r.weight, r.source or "", r.destination or "",
            r.in_interface or "", r.proto, r.destination_port or "", r.jump)


def _port_str(p: PortSpec) -> str | None:
    if p.port is None:
        return None
    return f"{p.port}:{p.port_end}" if p.port_end else str(p.port)


def _param(policy: NetworkPolicyTemplate, topology: Topology, key: str, default):
    """Resolve a policy param: topology override wins over template default."""
    return topology.network_policy.overrides.get(key, policy.params.get(key, default))


def compile_network_policy(
    topology: Topology, policy: NetworkPolicyTemplate, *, version: str
) -> CompiledNetworkPolicy:
    """Compile *policy* against *topology*'s zone/subnet bindings into FORWARD rules."""
    zsubnet = zone_subnet_map(topology)
    zbridge = zone_bridge_map(topology)
    services = {s.name: s for s in policy.services}
    wan_interface = _param(policy, topology, "wan_interface", "vmbr0")
    defaults = policy.defaults

    rules: list[CompiledRule] = []

    # band 0 — return traffic
    if defaults.accept_established_related:
        rules.append(CompiledRule(
            weight=W_ESTABLISHED, ctstate="ESTABLISHED,RELATED", jump="ACCEPT",
            comment="r42: allow established",
        ))

    # explicit matrix rules
    for mr in policy.matrix:
        rules.extend(_compile_matrix_rule(mr, zsubnet, services, topology, policy))

    # band 300 — intra-zone accept
    if defaults.allow_intra_zone:
        for zname, cidr in sorted(zsubnet.items()):
            rules.append(CompiledRule(
                weight=W_INTRA, source=cidr, destination=cidr, jump="ACCEPT",
                comment=f"r42: intra-zone {zname}",
            ))

    # band 600 — air-gap (zone bridge -> wan drop)
    for zname in defaults.airgap_zones:
        bridge = zbridge.get(zname)
        if bridge is None:
            continue
        rules.append(CompiledRule(
            weight=W_AIRGAP, in_interface=bridge, out_interface=wan_interface,
            source=zsubnet.get(zname), jump="DROP",
            comment=f"r42: air-gap {zname}",
        ))

    # band 900 — terminal default
    rules.append(CompiledRule(
        weight=W_DEFAULT, jump=_ACTION_JUMP[defaults.default_action],
        comment=f"r42: default {defaults.default_action}",
    ))

    rules.sort(key=_sort_key)
    return CompiledNetworkPolicy(
        policy_id=policy.id, policy_version=version,
        wan_interface=wan_interface, rules=rules,
    )


def _compile_matrix_rule(mr, zsubnet, services, topology, policy) -> list[CompiledRule]:
    jump = _ACTION_JUMP[mr.action]
    src = None if mr.src == "*" else zsubnet.get(mr.src)
    comment = f"r42: {mr.comment}" if mr.comment else f"r42: {mr.src}->{mr.dst}"

    # service destination (svc:<name>) -> one rule per service port
    if mr.dst.startswith(_SVC):
        svc_name = mr.dst[len(_SVC):]
        svc = services.get(svc_name)
        if svc is None:
            return []
        svc_ip = _param(policy, topology, f"{svc_name}_ip", None)
        out: list[CompiledRule] = []
        for p in (mr.ports or svc.ports):
            out.append(CompiledRule(
                weight=W_SERVICE_ACCEPT if mr.action == "accept" else W_ZONE_DROP,
                proto=p.proto, source=src, destination=svc_ip,
                destination_port=_port_str(p), jump=jump, comment=comment,
            ))
        return out

    # zone destination
    dst = zsubnet.get(mr.dst)
    weight = W_ZONE_ACCEPT if mr.action == "accept" else W_ZONE_DROP
    if mr.ports:
        return [CompiledRule(weight=weight, proto=p.proto, source=src, destination=dst,
                             destination_port=_port_str(p), jump=jump, comment=comment)
                for p in mr.ports]
    return [CompiledRule(weight=weight, source=src, destination=dst, jump=jump,
                         comment=comment)]


def lint_segmentation(
    compiled: CompiledNetworkPolicy, policy: NetworkPolicyTemplate, topology: Topology
) -> list[str]:
    """Assert the compiled rule table is safe. Returns problems ([] == safe)."""
    problems: list[str] = []
    rules = compiled.rules

    # 1. FORWARD only — host INPUT (SSH/mgmt) must never be touched
    if any(r.chain != "FORWARD" for r in rules):
        problems.append("non-FORWARD rule present (host INPUT must not be modified)")

    drop_weights = [r.weight for r in rules if r.jump in ("DROP", "REJECT")]
    first_drop = min(drop_weights) if drop_weights else None

    # 2. established accept must exist and precede any drop
    if policy.defaults.accept_established_related:
        est = [r for r in rules if r.ctstate and "ESTABLISHED" in r.ctstate and r.jump == "ACCEPT"]
        if not est:
            problems.append("missing ESTABLISHED,RELATED ACCEPT")
        elif first_drop is not None and min(r.weight for r in est) > first_drop:
            problems.append("ESTABLISHED accept does not precede DROP rules")

    zsubnet = zone_subnet_map(topology)

    # 3. each explicit deny pair must not be shadowed by an earlier accept
    for mr in policy.matrix:
        if mr.action not in ("drop", "reject"):
            continue
        if mr.dst.startswith(_SVC):
            continue
        src, dst = zsubnet.get(mr.src), zsubnet.get(mr.dst)
        if src is None or dst is None:
            continue
        drop_w = min((r.weight for r in rules
                      if r.source == src and r.destination == dst and r.jump in ("DROP", "REJECT")),
                     default=None)
        if drop_w is None:
            problems.append(f"deny {mr.src}->{mr.dst} produced no DROP rule")
            continue
        if any(r.source == src and r.destination == dst and r.jump == "ACCEPT" and r.weight < drop_w
               for r in rules):
            problems.append(f"ACCEPT shadows deny {mr.src}->{mr.dst} (ordering hazard)")

    # 4. each air-gap zone must have a wan-drop rule
    zbridge = zone_bridge_map(topology)
    for zname in policy.defaults.airgap_zones:
        bridge = zbridge.get(zname)
        if bridge and not any(r.in_interface == bridge and r.out_interface and r.jump == "DROP"
                              for r in rules):
            problems.append(f"air-gap zone {zname!r} missing wan DROP")

    # 5. default-deny must be the terminal rule
    if policy.defaults.default_action == "drop" and rules and rules[-1].jump != "DROP":
        problems.append("default-deny is not the terminal rule")

    return problems
