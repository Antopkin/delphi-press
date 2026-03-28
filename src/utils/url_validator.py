"""URL validation for SSRF protection.

Validates that URLs point to public internet addresses, blocking
private networks, loopback, link-local, and cloud metadata endpoints.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SSRFBlockedError(Exception):
    """Raised when a URL targets a private/blocked address."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"SSRF blocked: {reason} ({url})")


def validate_url_safe(url: str) -> None:
    """Validate that a URL is safe for server-side requests.

    Checks:
    1. Scheme is http or https.
    2. Hostname is not an IP literal in a private range.
    3. Hostname DNS resolution does not point to a private IP.

    Raises:
        SSRFBlockedError: If the URL targets a blocked address.
    """
    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFBlockedError(url, f"scheme '{parsed.scheme}' not allowed")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError(url, "no hostname")

    # Check if hostname is an IP literal
    try:
        addr = ipaddress.ip_address(hostname)
        if _is_blocked(addr):
            raise SSRFBlockedError(url, f"private IP {addr}")
        return
    except ValueError:
        pass  # Not an IP literal, proceed to DNS resolution

    # Resolve hostname and check all addresses
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return  # DNS failure — let the HTTP client handle it

    for family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
            if _is_blocked(addr):
                raise SSRFBlockedError(url, f"resolves to private IP {addr}")
        except ValueError:
            continue


def _is_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address falls within any blocked network."""
    return any(addr in network for network in _BLOCKED_NETWORKS)
