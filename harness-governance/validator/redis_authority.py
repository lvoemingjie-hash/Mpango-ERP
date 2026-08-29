"""HE2-ET1-R2-R1 shared stdlib Redis authority module.

THE single live-Redis implementation for the whole harness: the authority
runner's preflight AND the child plugin's pytest_sessionstart both import
THIS module (same file, same cached module object) — protocol code is
never duplicated.

Wire protocol: proper RESP arrays with bulk-string arguments (never
space-joined inline commands, which cannot carry spaces/CR/LF/special
characters safely).

Credentials: percent-decoded from the URL (urllib.parse.unquote).
  password only            -> AUTH <password>
  username + password      -> AUTH <username> <password>   (Redis 6 ACL)
  username without password -> fail closed (auth_misconfigured)

Sanitization contract: every outcome is a FIXED category string or
boolean — url_absent / url_malformed / wrong_db / auth_misconfigured /
connect_failed / auth_failed / ping_failed / select_failed / db_nonempty /
sentinel_reachable / tls_unsupported_fail_closed / ok. URLs, hosts, ports,
usernames, passwords, and Redis reply text NEVER appear in evidence,
proofs, logs, or exception text. All socket/SSL/protocol/parse failures
are mapped to these categories; no raw exception ever escapes
redis_live_check / eval_redis.
"""

from __future__ import annotations

import socket
import urllib.parse

REDIS_REQUIRED_DB = "15"
REDIS_SCHEMES = ("redis",)
REDIS_TIMEOUT_S = 2.0
SENTINEL_PROBE_ENDPOINT = ("127.0.0.1", 26379)

REDIS_CATEGORIES = frozenset(
    {
        "url_absent", "url_malformed", "wrong_db", "auth_misconfigured",
        "connect_failed", "auth_failed", "ping_failed", "select_failed",
        "db_nonempty", "sentinel_reachable", "tls_unsupported_fail_closed",
        "protocol_error", "ok",
    }
)


class RedisAuthorityError(Exception):
    """Sanitized live-check failure: `category` is a fixed label; the
    original OS/protocol exception is deliberately NOT chained into any
    published surface."""

    def __init__(self, category: str):
        super().__init__(f"redis_authority:{category}")
        self.category = category


def resp_encode(*parts) -> bytes:
    """RESP array of bulk strings (binary-safe for any argument bytes)."""
    out = bytearray(b"*" + str(len(parts)).encode("ascii") + b"\r\n")
    for part in parts:
        raw = part if isinstance(part, bytes) else str(part).encode("utf-8")
        out += b"$" + str(len(raw)).encode("ascii") + b"\r\n" + raw + b"\r\n"
    return bytes(out)


def _read_reply(reader):
    """Read one RESP2 reply: (kind, value). Error TEXT is dropped (servers
    may echo request bytes); unexpected kinds fail closed to ("error", None)."""
    line = reader.readline()
    if not line:
        return ("closed", None)
    line = line.rstrip(b"\r\n")
    kind, body = line[:1], line[1:]
    if kind == b"+":
        return ("simple", body.decode("utf-8", "replace"))
    if kind == b"-":
        return ("error", None)
    if kind == b":":
        try:
            return ("int", int(body))
        except ValueError:
            return ("error", None)
    if kind == b"$":
        try:
            length = int(body)
        except ValueError:
            return ("error", None)
        if length < 0:
            return ("null", None)
        payload = reader.read(length)
        if payload is None or len(payload) != length:
            return ("closed", None)
        if reader.read(2) != b"\r\n":
            return ("closed", None)
        return ("bulk", payload)
    return ("error", None)


def _cmd(reader, sock, parts):
    sock.sendall(resp_encode(*parts))
    return _read_reply(reader)


def _parse_url(url: str):
    """Percent-decode credentials; any malformed URL/port/IPv6 parse
    failure raises RedisAuthorityError('url_malformed') — never a raw
    ValueError."""
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port  # raises ValueError on ':notaport', out-of-range
        host = parsed.hostname  # raises ValueError on malformed IPv6
        # urlsplit returns EMPTY STRINGS (not None) for '://:pwd@host' and
        # '://user:@host' — normalize both to absent so the AUTH shape is
        # decided by genuinely present credentials.
        password = urllib.parse.unquote(parsed.password) if parsed.password else None
        username = urllib.parse.unquote(parsed.username) if parsed.username else None
    except (ValueError, UnicodeError):
        raise RedisAuthorityError("url_malformed")
    return parsed, host, (port if port is not None else 6379), username, password


def redis_live_check(url: str) -> dict:
    """Live authority probe against the URL's OWN host/port. Returns a
    sanitized dict on success; raises RedisAuthorityError(category) for
    every failure mode. No traceback ever escapes: every OS/SSL/protocol
    exception is mapped to a fixed category."""
    raw = (url or "").strip()
    if not raw:
        raise RedisAuthorityError("url_absent")
    parsed, host, port, username, password = _parse_url(raw)
    if parsed.scheme not in REDIS_SCHEMES:
        # rediss (TLS) is deliberately UNSUPPORTED this round: no verified
        # TLS deployment was proven, so the gate fails closed instead of
        # claiming untested support.
        if parsed.scheme == "rediss":
            raise RedisAuthorityError("tls_unsupported_fail_closed")
        raise RedisAuthorityError("url_malformed")
    if not host:
        raise RedisAuthorityError("url_malformed")
    if (parsed.path or "").strip("/") != REDIS_REQUIRED_DB:
        raise RedisAuthorityError("wrong_db")
    if username is not None and password is None:
        raise RedisAuthorityError("auth_misconfigured")
    try:
        sock = socket.create_connection((host, port), timeout=REDIS_TIMEOUT_S)
    except OSError:
        raise RedisAuthorityError("connect_failed")
    try:
        reader = sock.makefile("rb")
        if password is not None:
            auth_args = (username, password) if username is not None else (password,)
            if _cmd(reader, sock, ("AUTH", *auth_args)) != ("simple", "OK"):
                raise RedisAuthorityError("auth_failed")
        if _cmd(reader, sock, ("PING",)) != ("simple", "PONG"):
            raise RedisAuthorityError("ping_failed")
        if _cmd(reader, sock, ("SELECT", REDIS_REQUIRED_DB)) != ("simple", "OK"):
            raise RedisAuthorityError("select_failed")
        if _cmd(reader, sock, ("DBSIZE",)) != ("int", 0):
            raise RedisAuthorityError("db_nonempty")
        try:
            sock.sendall(resp_encode("QUIT"))
        except OSError:
            pass
    except RedisAuthorityError:
        raise
    except OSError:
        raise RedisAuthorityError("protocol_error")
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return {"redis": "ok", "ping_pong": True, "selected_db15": True,
            "dbsize_zero": True, "auth_used": password is not None,
            "acl_username_used": username is not None}


def require_sentinel_unreachable(endpoint=SENTINEL_PROBE_ENDPOINT) -> None:
    try:
        with socket.create_connection(endpoint, timeout=0.5):
            raise RedisAuthorityError("sentinel_reachable")
    except RedisAuthorityError:
        raise
    except OSError:
        return


def eval_redis(url: str, sentinel_endpoint=None) -> dict:
    """Live DB15 authority + sentinel unreachability (shared entrypoint)."""
    result = redis_live_check(url)
    require_sentinel_unreachable(
        sentinel_endpoint if sentinel_endpoint is not None else SENTINEL_PROBE_ENDPOINT
    )
    result["sentinel_26379"] = False
    return result
