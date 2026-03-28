"""Tests for src.utils.url_validator — SSRF protection."""

from unittest.mock import patch

import pytest

from src.utils.url_validator import SSRFBlockedError, validate_url_safe


# ── SSRF protection ─────────────────────────────────────────────────


def test_ssrf_private_ip_127_blocked():
    with pytest.raises(SSRFBlockedError):
        validate_url_safe("http://127.0.0.1/secret")


def test_ssrf_private_ip_10_blocked():
    with pytest.raises(SSRFBlockedError):
        validate_url_safe("http://10.0.0.1/admin")


def test_ssrf_private_ip_172_blocked():
    with pytest.raises(SSRFBlockedError):
        validate_url_safe("http://172.16.0.1/internal")


def test_ssrf_private_ip_192_blocked():
    with pytest.raises(SSRFBlockedError):
        validate_url_safe("http://192.168.1.1/router")


def test_ssrf_metadata_ip_blocked():
    with pytest.raises(SSRFBlockedError):
        validate_url_safe("http://169.254.169.254/latest/meta-data/")


def test_ssrf_file_scheme_blocked():
    with pytest.raises(SSRFBlockedError):
        validate_url_safe("file:///etc/passwd")


def test_ssrf_ftp_scheme_blocked():
    with pytest.raises(SSRFBlockedError):
        validate_url_safe("ftp://internal.server/data")


def test_ssrf_public_url_allowed():
    """Public HTTPS URLs must pass validation."""
    # Mock DNS to avoid real resolution
    with patch("src.utils.url_validator.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        validate_url_safe("https://example.com/page")


def test_ssrf_dns_resolves_to_private_blocked():
    """Hostname that resolves to private IP must be blocked."""
    with patch("src.utils.url_validator.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("127.0.0.1", 80))]
        with pytest.raises(SSRFBlockedError):
            validate_url_safe("http://evil.example.com/redirect")
