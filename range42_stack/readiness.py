"""Validate gateway DNS and report TLS-verified service readiness without exposing credentials."""
import argparse
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import sys
import urllib.request
from urllib.parse import urlsplit


def validate_dns(plan, gateway_addresses):
    expected = {str(ipaddress.ip_address(value)) for value in gateway_addresses}
    if not expected:
        raise ValueError('Declare at least one reachable gateway address')
    for endpoint in plan['endpoints'].values():
        host = urlsplit(endpoint).hostname
        try:
            addresses = {entry[4][0] for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        except OSError:
            raise ValueError('Gateway DNS is unavailable for ' + host) from None
        if not addresses or not addresses <= expected:
            raise ValueError('Gateway DNS points outside the declared addresses for ' + host)


def http_probe(url, token, ca):
    context = ssl.create_default_context(cafile=str(ca) if ca else None)
    # An authentication token must never follow a redirect to another host.
    class SameOrigin(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if urlsplit(newurl).netloc != urlsplit(req.full_url).netloc or urlsplit(newurl).scheme != 'https':
                raise ValueError('Unexpected cross-origin service redirect')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), SameOrigin())
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token} if token else {})
    with opener.open(request, timeout=15) as response:
        if not 200 <= response.status < 400:
            raise ValueError('Service returned an unsuccessful status')
        return json.load(response) if url.endswith('/health/ready') else {'ready': True}


def check_endpoints(plan, token, ca, probe=http_probe):
    services = {}
    for service, endpoint in plan['endpoints'].items():
        try:
            status = probe(endpoint + ('/v1/health/ready' if service == 'backend' else '/'),
                           token if service == 'backend' else None, ca)
            services[service] = {'ready': status.get('ready') is True}
        except Exception as error:
            # Exception URLs, response bodies and headers may contain credentials.
            services[service] = {'ready': False, 'error': type(error).__name__}
    return {'ready': bool(services) and all(s['ready'] for s in services.values()), 'services': services}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--input-stdin', action='store_true', help='Read {token, enabled} privately from stdin')
    parser.add_argument('--ca-file', type=Path)
    parser.add_argument('--enabled-file', type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    private = json.load(sys.stdin) if args.input_stdin else {}
    if args.enabled_file:
        enabled = json.loads(args.enabled_file.read_text())
        plan['endpoints'] = {k:v for k,v in plan['endpoints'].items() if enabled.get(k,True)}
    if 'enabled' in private:
        plan['endpoints'] = {k:v for k,v in plan['endpoints'].items() if private['enabled'].get(k,True)}
    token = private.get('token') or (args.token_file.read_text().strip() if args.token_file else '')
    result = check_endpoints(plan, token, args.ca_file)
    print(json.dumps(result))
    raise SystemExit(0 if result['ready'] else 1)


if __name__ == '__main__':
    main()
