import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

# Capture one frozen command. Selection, environment preparation and verdicts stay outside.
os.umask(0o077)
plan_path, call_id, env_path = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
plan_bytes = plan_path.read_bytes()
plan = json.loads(plan_bytes)
call = next(c for c in plan["commands"] if c["id"] == call_id)
environment = json.loads(env_path.read_text())
assert isinstance(environment, dict)
assert all(isinstance(k, str) and isinstance(v, str) for k, v in environment.items())
environment.update(call.get("nonsecret_environment_bindings", {}))
for key in call.get("remove_env", []):
    environment.pop(key, None)
assert isinstance(call["argv"], list) and call["argv"]
assert all(isinstance(arg, str) for arg in call["argv"])
cap = min(float(call["native_timeout_seconds"]), float(sys.argv[4])) if len(sys.argv) > 4 else call["native_timeout_seconds"]
assert cap > 0
paths = {k: Path(call[k + "_path"]) for k in ("stdout", "stderr", "intent", "record")}
paths["process"] = paths["intent"].with_suffix(".process.json")
for path in paths.values():
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
assert all(not path.exists() and not path.is_symlink() for path in paths.values())
record = {
    "id": call["id"],
    "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
    "argv": call["argv"],
    "cwd": call["cwd"],
    "env_key_names": sorted(environment),
    "invocation_id": call.get("invocation_id"),
    "timeout_seconds": cap,
    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "native_rc": None,
    "timed_out": False,
    "metadata_errors": [],
}
with os.fdopen(os.open(paths["intent"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
    json.dump(record, handle, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
started = time.monotonic()
process = None
with os.fdopen(os.open(paths["stdout"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stdout:
    with os.fdopen(os.open(paths["stderr"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stderr:
        try:
            process = subprocess.Popen(
                call["argv"], cwd=call["cwd"], env=environment,
                stdout=stdout, stderr=stderr, start_new_session=True,
            )
            record["pid"] = process.pid
            record["pgid"] = process.pid
            record["start_ticks"] = None
            try:
                tail = Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()
                record["start_ticks"] = int(tail[19])
            except (OSError, ValueError, IndexError) as error:
                record["metadata_errors"].append("proc_stat:" + type(error).__name__)
            try:
                with os.fdopen(os.open(paths["process"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
                    json.dump({k: record.get(k) for k in ("id", "pid", "pgid", "start_ticks", "started_at", "metadata_errors")}, handle)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as error:
                record["metadata_errors"].append("process_record:" + type(error).__name__)
            try:
                record["native_rc"] = process.wait(timeout=cap)
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                try:
                    record["native_rc"] = process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    record["native_rc"] = process.wait()
        except OSError as error:
            record["launch_or_wait_error"] = type(error).__name__
        finally:
            # Metadata trouble must never skip the actual child's wait/returncode.
            if process is not None and record["native_rc"] is None:
                record["native_rc"] = process.wait()
record["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
record["elapsed_seconds"] = time.monotonic() - started
record["outputs"] = {}
for kind in ("stdout", "stderr"):
    data = paths[kind].read_bytes()
    record["outputs"][kind] = {
        "path": str(paths[kind]), "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
with os.fdopen(os.open(paths["record"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
    json.dump(record, handle, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
print(json.dumps({"id": call["id"], "native_rc": record["native_rc"], "timed_out": record["timed_out"]}))
sys.exit(124 if record["timed_out"] else (record["native_rc"] if isinstance(record["native_rc"], int) and 0 <= record["native_rc"] <= 125 else 1))
