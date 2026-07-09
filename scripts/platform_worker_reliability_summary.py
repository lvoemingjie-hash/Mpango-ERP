#!/usr/bin/env python3
"""Platform Worker Reliability Summary CLI - Mpango ERP.

Reads platform worker result JSON and events JSONL files,
producing a summary of worker reliability metrics.
"""

import argparse
import json
import os
import sys


LEDGER_DIR = "ai-ledger/platform"


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None
    except Exception:
        return None


def load_events_jsonl(path):
    events = []
    malformed = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    malformed += 1
    except Exception:
        pass
    return events, malformed


def summarize_results(repo_root):
    """Scan result JSONs and produce reliability summary."""
    ledger_dir = os.path.join(repo_root, LEDGER_DIR)
    summary = {
        "total_missions": 0,
        "results": {
            "done": 0,
            "partial": 0,
            "failed": 0,
            "unknown": 0,
        },
        "timeouts": 0,
        "nonzero_exit": 0,
        "malformed_artifacts": 0,
        "missing_artifacts": 0,
        "sanitized_events": 0,
        "unsanitized_events": 0,
        "elapsed": [],
        "details": [],
    }

    if not os.path.isdir(ledger_dir):
        return summary

    # Find all mission JSONs to get result/events references
    all_files = os.listdir(ledger_dir)
    mission_jsons = sorted(f for f in all_files if f.endswith("_mission.json"))

    for mj in mission_jsons:
        mj_path = os.path.join(ledger_dir, mj)
        data = load_json(mj_path)
        if data is None:
            summary["malformed_artifacts"] += 1
            continue

        summary["total_missions"] += 1
        detail = {"mission": mj, "status": "unknown"}

        # Check result
        result_ref = data.get("result", "")
        if isinstance(result_ref, str) and result_ref.strip():
            result_abs = os.path.join(repo_root, result_ref.replace("\\", "/"))
            result_data = load_json(result_abs)
            if result_data is None:
                if os.path.isfile(result_abs):
                    summary["malformed_artifacts"] += 1
                    detail["result"] = "malformed"
                else:
                    summary["missing_artifacts"] += 1
                    detail["result"] = "missing"
            else:
                status = result_data.get("status", "unknown")
                detail["status"] = status
                if status in ("done", "partial", "failed"):
                    summary["results"][status] += 1
                else:
                    summary["results"]["unknown"] += 1

                blocker = result_data.get("blocker", "")
                if "timeout" in blocker.lower() or "timed out" in blocker.lower():
                    summary["timeouts"] += 1
                    detail["timeout"] = True

                test_result = result_data.get("test_result", "")
                if "timeout" in test_result.lower():
                    if "timeout" not in blocker.lower():
                        summary["timeouts"] += 1
                        detail["timeout"] = True
        else:
            detail["result"] = "no_ref"

        # Check events
        events_ref = data.get("events", "")
        if isinstance(events_ref, str) and events_ref.strip():
            events_abs = os.path.join(repo_root, events_ref.replace("\\", "/"))
            if os.path.isfile(events_abs):
                events, mal = load_events_jsonl(events_abs)
                summary["malformed_artifacts"] += mal

                for ev in events:
                    if ev.get("timed_out"):
                        if not detail.get("timeout"):
                            summary["timeouts"] += 1
                            detail["timeout"] = True
                    exit_code = ev.get("exit_code")
                    if isinstance(exit_code, int) and exit_code != 0:
                        summary["nonzero_exit"] += 1
                        detail["nonzero_exit"] = True
                    elapsed = ev.get("elapsed_seconds")
                    if isinstance(elapsed, (int, float)):
                        summary["elapsed"].append(elapsed)
                    if ev.get("redacted"):
                        summary["sanitized_events"] += 1
                    else:
                        summary["unsanitized_events"] += 1
            else:
                summary["missing_artifacts"] += 1
                detail["events"] = "missing"

        summary["details"].append(detail)

    return summary


def compute_elapsed_stats(elapsed_list):
    if not elapsed_list:
        return {"min": None, "max": None, "mean": None, "count": 0}
    return {
        "min": round(min(elapsed_list), 2),
        "max": round(max(elapsed_list), 2),
        "mean": round(sum(elapsed_list) / len(elapsed_list), 2),
        "count": len(elapsed_list),
    }


def format_human(summary):
    lines = ["Platform Worker Reliability Summary", "=" * 40, ""]
    lines.append(f"Missions scanned: {summary['total_missions']}")
    lines.append("")
    lines.append("Status breakdown:")
    for status in ("done", "partial", "failed", "unknown"):
        lines.append(f"  {status}: {summary['results'][status]}")
    lines.append("")
    lines.append(f"Timeouts:           {summary['timeouts']}")
    lines.append(f"Nonzero exits:      {summary['nonzero_exit']}")
    lines.append(f"Malformed artifacts: {summary['malformed_artifacts']}")
    lines.append(f"Missing artifacts:   {summary['missing_artifacts']}")
    lines.append("")

    elapsed = compute_elapsed_stats(summary["elapsed"])
    lines.append("Elapsed seconds:")
    if elapsed["count"] > 0:
        lines.append(f"  min:  {elapsed['min']}")
        lines.append(f"  max:  {elapsed['max']}")
        lines.append(f"  mean: {elapsed['mean']}")
        lines.append(f"  count: {elapsed['count']}")
    else:
        lines.append("  (no elapsed data)")
    lines.append("")

    lines.append("Event sanitization:")
    lines.append(f"  sanitized:   {summary['sanitized_events']}")
    lines.append(f"  unsanitized: {summary['unsanitized_events']}")

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Platform Worker Reliability Summary"
    )
    parser.add_argument("--repo", required=True, help="Path to repository root")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args(argv)

    repo_root = os.path.abspath(args.repo)
    if not os.path.isdir(repo_root):
        print(f"Error: {args.repo} is not a directory", file=sys.stderr)
        return 2

    summary = summarize_results(repo_root)

    if args.json:
        output = dict(summary)
        output["elapsed_stats"] = compute_elapsed_stats(summary["elapsed"])
        del output["elapsed"]
        print(json.dumps(output, indent=2))
    else:
        print(format_human(summary))

    return 0


if __name__ == "__main__":
    sys.exit(main())
