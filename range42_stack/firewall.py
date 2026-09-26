"""Generate guest-local nftables rules, including Docker's forwarded ingress."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import sys

from .render import node


def render_firewall(plan, service, interface, policy):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,14}", interface):
        raise ValueError("Invalid guest ingress interface")
    networks = {}
    for key in ("management", "clients", "agents"):
        values = policy.get(key, [])
        if not isinstance(values, list) or len(values) > 64 or (key == "management" and not values):
            raise ValueError("Supply explicit management CIDRs and bounded ingress lists")
        networks[key] = [str(ipaddress.IPv4Network(value, strict=True)) for value in values]
    def addresses(values):
        return "{ " + ", ".join(values) + " }"
    gateway = node(plan, "gateway")["ip"]
    inbound = [f"ip saddr {addresses(networks['management'])} tcp dport 22 accept"]
    if service == "wazuh":
        inbound.append(f"ip saddr {gateway} tcp dport 443 accept")
        if networks["agents"]:
            inbound.append(f"ip saddr {addresses(networks['agents'])} tcp dport {{ 1514, 1515, 55000 }} accept")
    if service == "gateway":
        if networks["clients"]:
            inbound.append(f"ip saddr {addresses(networks['clients'])} tcp dport 443 accept")
        forwarded = ([f'iifname "{interface}" ct status dnat ip saddr {addresses(networks["clients"])} tcp dport 8443 accept']
                     if networks["clients"] else [])
    else:
        forwarded = [f'iifname "{interface}" ct status dnat ip saddr {gateway} accept']
    forwarded.append(f'iifname "{interface}" ct status dnat drop')
    table = "r42_" + plan["id"].replace("-", "_")
    return f"""add table inet {table}
flush table inet {table}
table inet {table} {{
 chain input {{
  type filter hook input priority -10; policy drop;
  iifname "lo" accept
  ct state established,related accept
  ip protocol icmp accept
  icmpv6 type {{ nd-neighbor-solicit, nd-neighbor-advert, nd-router-advert }} accept
  {chr(10).join(inbound)}
 }}
 chain forward {{
  type filter hook forward priority -10; policy accept;
  ct state established,related accept
  {chr(10).join(forwarded)}
 }}
}}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--interface", required=True)
    args = parser.parse_args()
    print(render_firewall(json.loads(args.plan.read_text()), args.service, args.interface, json.load(sys.stdin)))


if __name__ == "__main__":
    main()
