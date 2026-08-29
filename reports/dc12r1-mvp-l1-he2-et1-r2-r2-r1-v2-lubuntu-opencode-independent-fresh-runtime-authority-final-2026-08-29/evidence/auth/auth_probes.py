"""Live AUTH +/- path probes for DC-12R1 V2 final authority run.

Library-level probes against REAL redis containers using the candidate's
shared stdlib module (harness-governance/validator/redis_authority.py).
No authority command is launched by this script (no runner invocation).
Output: one JSON line per probe, sanitized (no credentials, no URLs).
"""
import importlib.util
import json
import os
import sys

RUNNER = "harness-governance/validator/authority_runner.py"
spec = importlib.util.spec_from_file_location("ra_mod", RUNNER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

RP_URL = os.environ["PW1R3_TEST_REDIS_URL"]            # requirepass container, correct pass
RP_WRONG = RP_URL.replace(
    f":{os.environ['REDIS_PASS']}@", ":wrongpass0000000000000000000000000@")
ACL_USER = os.environ["ACL_USER"]
ACL_PASS = os.environ["ACL_PASS"]
ACL_URL_OK = f"redis://{ACL_USER}:{ACL_PASS}@127.0.0.1:16380/15"
ACL_URL_NO_PASS = f"redis://{ACL_USER}@127.0.0.1:16380/15"
PLAIN_URL = "redis://127.0.0.1:16380/15"
SENTINEL = ("127.0.0.1", 26379)


def sanitize(result):
    if isinstance(result, dict):
        clean = {}
        for k, v in result.items():
            if any(t in k for t in ("password", "credential", "url", "host")):
                clean[k] = "<redacted>"
            else:
                clean[k] = sanitize(v)
        return clean
    return result


def probe(name, fn):
    try:
        r = fn()
        print(json.dumps({"probe": name, "outcome": "ok", "detail": sanitize(r)}))
    except mod.TrapFired as e:
        print(json.dumps({"probe": name, "outcome": "fail_closed",
                          "trap_id": e.trap_id, "evidence": sanitize(e.evidence)}))
    except Exception as e:  # noqa: BLE001 - evidence: unexpected is a failure signal
        print(json.dumps({"probe": name, "outcome": "UNEXPECTED",
                          "exc_type": type(e).__name__}))


# requirepass positive: correct password in URL AUTHs -> ok
probe("requirepass_positive_correct_password", lambda: mod.redis_live_check(RP_URL))
# requirepass negative: wrong password -> fail closed, sanitized
probe("requirepass_negative_wrong_password", lambda: mod.redis_live_check(RP_WRONG))
# ACL positive: username+password two-arg AUTH -> ok
probe("acl_positive_username_password", lambda: mod.redis_live_check(ACL_URL_OK))
# ACL negative: username without password -> fail closed auth_misconfigured
probe("acl_negative_username_without_password", lambda: mod.redis_live_check(ACL_URL_NO_PASS))
# baseline sanity: plain URL on suite container -> ok
probe("plain_positive_no_auth_container", lambda: mod.redis_live_check(PLAIN_URL))
# malformed URLs -> sanitized fail-closed, no traceback
probe("malformed_url_scheme_missing", lambda: mod.redis_live_check("127.0.0.1:16380/15"))
probe("malformed_url_bracket_ipv6", lambda: mod.redis_live_check("redis://[::1:16380/15"))
probe("malformed_url_double_port", lambda: mod.redis_live_check("redis://127.0.0.1:16380:9999/15"))
probe("malformed_url_db_not_integer", lambda: mod.redis_live_check("redis://127.0.0.1:16380/fifteen"))
# rediss rejected fail closed (no unverified TLS claim)
probe("rediss_tls_rejected", lambda: mod.redis_live_check("rediss://127.0.0.1:16380/15"))
# sentinel unreachability gate itself (direct shared-module probe)
_ra_spec = importlib.util.spec_from_file_location(
    "et1_redis_authority_probe", "harness-governance/validator/redis_authority.py")
_ra = importlib.util.module_from_spec(_ra_spec)
_ra_spec.loader.exec_module(_ra)
try:
    _ra.require_sentinel_unreachable(SENTINEL)
    print(json.dumps({"probe": "sentinel_26379_unreachable_gate", "outcome": "ok"}))
except _ra.RedisAuthorityError:
    print(json.dumps({"probe": "sentinel_26379_unreachable_gate",
                      "outcome": "fail_closed", "category": "sentinel_reachable"}))
