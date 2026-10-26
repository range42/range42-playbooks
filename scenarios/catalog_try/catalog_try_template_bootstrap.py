#!/usr/bin/env python3
"""Prepare only native catalog template 9221 after authenticated admission."""
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml


class BootstrapError(ValueError):
    """A fixed diagnostic that never includes native credentials or responses."""


def safe_arguments(arguments):
    """Keep analysis switches while preventing target/inventory overrides."""
    index = 0
    allowed = {'--check', '-C', '--diff', '-D', '--syntax-check', '--list-hosts',
               '--list-tasks', '--list-tags', '-v', '-vv', '-vvv', '-vvvv'}
    while index < len(arguments):
        value = arguments[index]
        if value in allowed:
            index += 1
        elif value in ('-e', '--extra-vars') and arguments[index:index + 2] == [value, 'proxmox_api_validate_certs=true']:
            index += 2
        else:
            raise BootstrapError('Template bootstrap permits only read-only analysis switches and verified TLS')
    return arguments


class NativeAPI:
    def __init__(self, context, password):
        result = subprocess.run(['ansible-vault', 'view', str(context / 'secrets/default_vault.yml'),
            '--vault-password-file', str(password)], capture_output=True, text=True, timeout=30, check=False)
        if result.returncode:
            raise BootstrapError('The selected protected native context could not be read')
        values = yaml.safe_load(result.stdout)
        if not isinstance(values, dict):
            raise BootstrapError('The selected native context is invalid')
        required = ('proxmox_api_host', 'proxmox_node', 'proxmox_api_user',
                    'proxmox_api_token_id', 'proxmox_api_token_secret')
        if any(not isinstance(values.get(key), str) or not values[key] or '\n' in values[key]
               or '\r' in values[key] for key in required):
            raise BootstrapError('The selected native PVE credentials are incomplete')
        host, node = values['proxmox_api_host'], values['proxmox_node']
        endpoint = urllib.parse.urlsplit('https://' + host)
        if (not endpoint.hostname or endpoint.username or endpoint.password or endpoint.path
                or endpoint.query or endpoint.fragment or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,62}', node) is None):
            raise BootstrapError('The selected native PVE endpoint is invalid')
        if endpoint.port is not None and not 1 <= endpoint.port <= 65535:
            raise BootstrapError('The selected native PVE endpoint is invalid')
        self.base = 'https://' + host + '/api2/json/nodes/' + node + '/qemu'
        self.authorization = ('PVEAPIToken=' + values['proxmox_api_user'] + '!'
            + values['proxmox_api_token_id'] + '=' + values['proxmox_api_token_secret'])
        ca_file = os.environ.get('RANGE42_PROXMOX_CA_FILE') or None
        self.context = ssl.create_default_context(cafile=ca_file)

    def read(self, suffix=''):
        request = urllib.request.Request(self.base + suffix, headers={'Authorization': self.authorization})
        # A redirect must never forward the native token to another endpoint.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *_):
                return None
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=self.context))
        with opener.open(request, timeout=15) as response:
            payload = response.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise BootstrapError('Native template inventory exceeds its bound')
        document = json.loads(payload)
        if not isinstance(document, dict) or 'data' not in document:
            raise BootstrapError('Native template inventory is invalid')
        return document['data']

    def retained_template(self):
        rows = self.read()
        if not isinstance(rows, list) or len(rows) > 4096:
            raise BootstrapError('Native template inventory is invalid')
        ids = set()
        for row in rows:
            if (not isinstance(row, dict) or type(row.get('vmid')) is not int
                    or row['vmid'] <= 0 or row['vmid'] in ids):
                raise BootstrapError('Native template inventory is invalid or ambiguous')
            ids.add(row['vmid'])
        if 9221 not in ids:
            return False
        template = self.read('/9221/config')
        if (not isinstance(template, dict) or template.get('name') != 'template-vm-small-01-4g-32g'
                or type(template.get('template')) is not int or template['template'] != 1):
            raise BootstrapError('VMID 9221 is not the declared native template; no mutation was attempted')
        return True


def main():
    try:
        arguments = safe_arguments(sys.argv[1:])
        context = Path(os.environ['RANGE42_ACTIVE_CONFIG_DIR'])
        password = Path(os.environ['RANGE42_VAULT_PASSWORD_FILE'])
        inventory = Path(os.environ['RANGE42_ANSIBLE_ROLES__INVENTORY_DIR']) / 'inventory_default.yml'
        if NativeAPI(context, password).retained_template():
            print(':: exact native template 9221 is retained; all template, image and network mutations skipped')
            return 0
        playbook = Path(__file__).resolve().with_name('main_templates_only.yml')
        result = subprocess.run(['ansible-playbook', '-i', str(inventory), '-l', 'all', str(playbook),
            '--vault-password-file', str(password), '-e', 'proxmox_api_validate_certs=true', *arguments], check=False)
        return result.returncode
    except (BootstrapError, OSError, ValueError, KeyError, yaml.YAMLError, subprocess.SubprocessError):
        print('ERROR: Native template bootstrap stopped; review selected context, verified TLS and VMID 9221.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
