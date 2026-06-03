"""Compile a symbolic network policy + topology bindings into ordered FORWARD rules.

iptables FORWARD is first-match-wins, so rule ORDER is correctness, not style.
Each emitted rule gets a deterministic ``weight`` from a fixed band table; the
final list is stable-sorted by (weight, source, destination, proto, port, jump)
so identical inputs yield byte-identical output. The deploy playbook (Plan B)
flush-rebuilds a dedicated ``R42-FORWARD`` chain from this list in order, which
is naturally idempotent and never touches the host INPUT chain (SSH stays up).
"""

import ipaddress
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from r42playbooks.core import constants as C
from r42playbooks.core.catalog_models import MatrixRule, NetworkPolicyTemplate, PortSpec
from r42playbooks.core.errors import CompileError
from r42playbooks.core.models import Topology
from r42playbooks.core.validate import zone_bridge_map, zone_subnet_map

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
    destination_port: str | None = Field(default=None, pattern=C.PORT_SPEC_RE.pattern)
    in_interface: str | None = Field(default=None, pattern=C.IFACE_RE.pattern)
    out_interface: str | None = Field(default=None, pattern=C.IFACE_RE.pattern)
    ctstate: str | None = None
    jump: Literal["ACCEPT", "DROP", "REJECT"]
    comment: str = Field(max_length=200)


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


def _require_ip(value, what: str) -> str:
    """Validate that *value* is a concrete IPv4/IPv6 address, else CompileError."""
    try:
        ipaddress.ip_address(str(value))
    except ValueError:
        raise CompileError(f"{what} must be a valid IP address, got {value!r}") from None
    return str(value)


def compile_network_policy(
    topology: Topology, policy: NetworkPolicyTemplate, *, version: str
) -> CompiledNetworkPolicy:
    """Compile *policy* against *topology*'s zone/subnet bindings into FORWARD rules."""
    zsubnet = zone_subnet_map(topology)
    zbridge = zone_bridge_map(topology)
    services = {s.name: s for s in policy.services}
    wan_interface = str(_param(policy, topology, "wan_interface", "vmbr0"))
    if not C.IFACE_RE.fullmatch(wan_interface):
        raise CompileError(f"invalid wan_interface: {wan_interface!r}")
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
            raise CompileError(f"matrix references unknown service {svc_name!r}")
        # a missing/invalid service IP would silently broaden the rule to "any dest"
        svc_ip = _require_ip(_param(policy, topology, f"{svc_name}_ip", None),
                             f"service {svc_name!r} ip ({svc_name}_ip)")
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

    # 3. no ACCEPT may shadow an earlier-evaluated DROP/REJECT for overlapping
    #    traffic. Considers ALL compiled drops (including wildcard-source ones),
    #    not just exact matrix zone-pairs — this closes the src="*" bypass.
    #    The terminal default catch-all (no match fields) is excluded: specific
    #    ACCEPTs are *supposed* to precede it. Interface-scoped rules (air-gap)
    #    only conflict with other interface-scoped rules, so they are matched
    #    on interface too, avoiding false positives against CIDR/service rules.
    accepts = [r for r in rules if r.jump == "ACCEPT"]
    for d in rules:
        if d.jump not in ("DROP", "REJECT") or _is_catch_all(d):
            continue
        for a in accepts:
            if a.weight < d.weight and _shadows(a, d):
                problems.append(
                    f"ACCEPT (w{a.weight}) shadows DROP (w{d.weight}) for "
                    f"{a.source or '*'}->{a.destination or a.out_interface or '*'} "
                    f"({d.comment})"
                )
                break

    # also assert every explicit zone->zone deny actually produced a DROP rule
    zsubnet = zone_subnet_map(topology)
    for mr in policy.matrix:
        if mr.action not in ("drop", "reject") or mr.dst.startswith(_SVC) or mr.src == "*":
            continue
        src, dst = zsubnet.get(mr.src), zsubnet.get(mr.dst)
        if src is None or dst is None:
            continue
        if not any(r.source == src and r.destination == dst and r.jump in ("DROP", "REJECT")
                   for r in rules):
            problems.append(f"deny {mr.src}->{mr.dst} produced no DROP rule")

    # 4. each air-gap zone must exist in the topology AND have a wan-drop rule
    zbridge = zone_bridge_map(topology)
    for zname in policy.defaults.airgap_zones:
        bridge = zbridge.get(zname)
        if bridge is None:
            problems.append(f"air-gap zone {zname!r} not bound in topology — air-gap absent")
        elif not any(r.in_interface == bridge and r.out_interface and r.jump == "DROP"
                     for r in rules):
            problems.append(f"air-gap zone {zname!r} missing wan DROP")

    # 5. terminal rule must be the deny catch-all when default denies
    if policy.defaults.default_action in ("drop", "reject"):
        if not rules or rules[-1].jump not in ("DROP", "REJECT"):
            problems.append("default-deny is not the terminal rule")

    return problems


def _is_catch_all(rule: CompiledRule) -> bool:
    """True for a rule with no match fields — the intended terminal default."""
    return (rule.source is None and rule.destination is None
            and rule.in_interface is None and rule.out_interface is None
            and rule.destination_port is None and rule.ctstate is None)


def _shadows(accept: CompiledRule, drop: CompiledRule) -> bool:
    """True if *accept* would match traffic the later *drop* intends to block.

    A None match field means "any" for that dimension. Interface-scoped drops
    (air-gap) only conflict with interface-scoped accepts on the same interface,
    so they never false-positive against CIDR/service ACCEPT rules.
    """
    if drop.in_interface or drop.out_interface:
        return (accept.in_interface == drop.in_interface
                and accept.out_interface == drop.out_interface)
    src_overlap = drop.source is None or accept.source == drop.source
    dst_overlap = drop.destination is None or accept.destination == drop.destination
    return src_overlap and dst_overlap
