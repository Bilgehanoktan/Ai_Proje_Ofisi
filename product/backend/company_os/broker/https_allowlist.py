"""MOD-006/MOD-007: Fail-closed HTTPS allowlist and SSRF guard for external tool adapters."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import urllib.error
import urllib.parse
import urllib.request


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent 3xx redirects from pivoting an allowlisted request to an unapproved host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(req.full_url, code, f"REDIRECT_BLOCKED:{msg}", headers, fp)


def _is_forbidden_ip_literal(host: str, *, allow_loopback: bool) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if addr.is_loopback:
        return not allow_loopback
    return (
        addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


@dataclass(frozen=True)
class HttpsAllowlistPolicy:
    """Strict domain allowlist and SSRF policy for external read-only HTTP(S) adapters."""

    allowed_domains: frozenset[str]
    allow_loopback_http: bool = False
    max_response_bytes: int = 512 * 1024
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        normalized = frozenset(d.strip().lower().rstrip(".") for d in self.allowed_domains if d.strip())
        object.__setattr__(self, "allowed_domains", normalized)
        if self.max_response_bytes <= 0:
            raise ValueError("MAX_RESPONSE_BYTES_POSITIVE_REQUIRED")
        if self.timeout_seconds <= 0:
            raise ValueError("TIMEOUT_POSITIVE_REQUIRED")

    def validate_url(self, url: str) -> str:
        """Validate URL against scheme, credential, SSRF IP, and domain allowlist rules."""
        if type(url) is not str or not url.strip():
            raise ValueError("URL_REQUIRED")
        cleaned = url.strip()
        parsed = urllib.parse.urlparse(cleaned)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("CREDENTIALS_IN_URL_FORBIDDEN")
        if not parsed.hostname:
            raise ValueError("HOSTNAME_REQUIRED")
        host = parsed.hostname.lower().rstrip(".")
        if _is_forbidden_ip_literal(host, allow_loopback=self.allow_loopback_http):
            raise PermissionError("SSRF_IP_BLOCKED")
        is_loopback = host in ("localhost", "127.0.0.1", "::1")
        if is_loopback:
            if not self.allow_loopback_http:
                raise PermissionError("LOOPBACK_NOT_ALLOWED")
            if parsed.scheme not in ("http", "https"):
                raise ValueError("INVALID_SCHEME")
        else:
            if parsed.scheme != "https":
                raise PermissionError("HTTPS_REQUIRED")
        if host not in self.allowed_domains:
            raise PermissionError("DOMAIN_NOT_ALLOWLISTED")
        return cleaned

    def fetch_bounded(self, url: str) -> bytes:
        """Fetch an allowlisted URL with proxy disabled, redirects blocked, and byte cap enforced."""
        validated = self.validate_url(url)
        req = urllib.request.Request(validated, method="GET")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _RejectRedirects())
        with opener.open(req, timeout=self.timeout_seconds) as resp:
            data = resp.read(self.max_response_bytes + 1)
            if len(data) > self.max_response_bytes:
                raise ValueError("RESPONSE_SIZE_LIMIT_EXCEEDED")
            return data
