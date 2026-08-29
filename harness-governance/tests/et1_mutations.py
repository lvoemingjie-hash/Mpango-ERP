"""HE2-ET1 mutation additions: registry/profile tamper cases + GREEN controls.

Extends run_red_mutations (do NOT modify the existing 37 RED / 5 GREEN —
they are appended via this module's ET1_MUTATIONS / ET1_GREEN_CONTROLS and
wired in by run_red_mutations.py's ET1 hook).

Each RED mutation tampers a pristine workspace copy of the ET1 artifacts
(execution-traps.json / authority-profiles.json) and MUST turn the
validator RED with the intended ET1 rule code. GREEN controls prove the
pristine registry/profile set stays GREEN.
"""

import json
import os

ET1_TRAPS = "harness-governance/inventory/execution-traps.json"
ET1_PROFILES = "harness-governance/inventory/authority-profiles.json"


def _traps(root):
    with open(os.path.join(root, ET1_TRAPS), encoding="utf-8") as fh:
        return json.load(fh)


def _save_traps(head, doc):
    with open(os.path.join(head, ET1_TRAPS), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _profiles(root):
    with open(os.path.join(root, ET1_PROFILES), encoding="utf-8") as fh:
        return json.load(fh)


def _save_profiles(head, doc):
    with open(os.path.join(head, ET1_PROFILES), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _trap(head, trap_id):
    doc = _traps(head)
    trap = next(t for t in doc["traps"] if t["trap_id"] == trap_id)
    return doc, trap


# --- ET1 RED mutation factories --------------------------------------------


def et1_mut_trap_deleted(head, _base):
    doc = _traps(head)
    doc["traps"] = [t for t in doc["traps"] if t["trap_id"] != "TRAP_PG_ROLE_SUPER"]
    _save_traps(head, doc)


def et1_mut_p0_disabled(head, _base):
    doc, trap = _trap(head, "TRAP_TEST_DB_URL_EMPTY")
    trap["status"] = "RETIRED"
    _save_traps(head, doc)


def et1_mut_exit_code_conflict(head, _base):
    doc, trap = _trap(head, "TRAP_MIXED_EOF")
    trap["stable_exit_code"] = 10  # collides with TRAP_PG_ROLE_SUPER
    _save_traps(head, doc)


def et1_mut_unknown_evaluator(head, _base):
    doc, trap = _trap(head, "TRAP_REDIS_WRONG_DB")
    trap["evaluator_id"] = "EVAL_SHELL_INJECTION"
    _save_traps(head, doc)


def et1_mut_negative_control_removed(head, _base):
    doc, trap = _trap(head, "TRAP_ALEMBIC_MULTI_HEAD")
    trap["negative_control_id"] = ""
    _save_traps(head, doc)


def et1_mut_p0p1_unreferenced(head, _base):
    doc = _profiles(head)
    for profile in doc["profiles"]:
        profile["required_traps"] = [
            t for t in profile["required_traps"] if t != "TRAP_JIT_ROLE_ESCALATION"
        ]
    _save_profiles(head, doc)


def et1_mut_profile_unknown_trap(head, _base):
    doc = _profiles(head)
    doc["profiles"][0]["required_traps"].append("TRAP_DOES_NOT_EXIST")
    _save_profiles(head, doc)


def et1_mut_registry_unreadable(head, _base):
    with open(os.path.join(head, ET1_TRAPS), "w", encoding="utf-8") as fh:
        fh.write("{not json")


def et1_mut_profiles_missing(head, _base):
    os.remove(os.path.join(head, ET1_PROFILES))


def et1_mut_second_trap_deleted(head, _base):
    doc = _traps(head)
    doc["traps"] = [t for t in doc["traps"] if t["trap_id"] != "TRAP_PHASE_CONTINUE_AFTER_FAIL"]
    _save_traps(head, doc)


def et1_mut_shell_command_in_registry(head, _base):
    doc, trap = _trap(head, "TRAP_MIXED_EOF")  # schema rejects the extra key
    trap["evaluator_command"] = "bash -c 'echo pwned'"
    _save_traps(head, doc)


def et1_mut_risk_downgrade_p0_to_p3(head, _base):
    doc, trap = _trap(head, "TRAP_COLLECT_NODE_SET_DRIFT")
    trap["risk"] = "CRITICAL"  # not in the schema enum
    _save_traps(head, doc)


def et1_mut_exit_code_zero(head, _base):
    doc, trap = _trap(head, "TRAP_SESSIONSTART_DRIFT")
    trap["stable_exit_code"] = 0  # schema minimum 10
    _save_traps(head, doc)


def et1_mut_stop_phase_weakened(head, _base):
    doc, trap = _trap(head, "TRAP_PG_ROLE_SUPER")
    trap["stop_phase"] = "WHENEVER"  # schema enum violation
    _save_traps(head, doc)


# --- ET1 GREEN controls -----------------------------------------------------


def et1_control_pristine(head, _base):
    return None  # pristine workspace is already the GREEN state


def et1_control_trap_renumbered_consistently(head, base):
    """Renumbering exit codes uniquely in BOTH trees stays GREEN (no drift)."""
    for root in (head, base):
        doc = _traps(root)
        for index, trap in enumerate(doc["traps"], start=50):
            trap["stable_exit_code"] = index
        _save_traps(root, doc)


def et1_control_profile_extended(head, base):
    """Adding a well-formed profile in BOTH trees stays GREEN."""
    for root in (head, base):
        doc = _profiles(root)
        doc["profiles"].append(
            {
                "profile_id": "AUTHORITY_EXTRA",
                "description": "additional profile referencing existing traps",
                "required_traps": ["TRAP_PG_ROLE_SUPER", "TRAP_MIXED_EOF"],
                "phases": ["PREFLIGHT"],
                "runner": "harness-governance/validator/authority_runner.py",
                "status": "CANDIDATE",
                "expected_alembic_head": "037_payment_declarations_schema",
            }
        )
        _save_profiles(root, doc)


def et1_control_trap_added(head, base):
    """Adding a NEW well-formed P2 trap in BOTH trees stays GREEN."""
    for root in (head, base):
        doc = _traps(root)
        doc["traps"].append(
            {
                "trap_id": "TRAP_ET1_EXTRA_P2",
                "category": "environment",
                "risk": "P2",
                "applies_to": ["runner.preflight"],
                "evaluator_id": "EVAL_TEST_DB_URL",
                "stop_phase": "PREFLIGHT",
                "stable_exit_code": 77,
                "required_evidence": ["some invariant"],
                "forbidden_next_phases": ["RUNNING"],
                "negative_control_id": "NC_ET1_EXTRA",
                "owner": "CTO",
                "remediation": "fix the invariant",
                "source_evidence_refs": ["HE2-ET1"],
                "status": "ACTIVE",
            }
        )
        _save_traps(root, doc)


ET1_MUTATIONS = [
    ("E01-trap-deleted", et1_mut_trap_deleted, ["ET1-TRAP-DELETED"], ()),
    ("E02-p0-disabled", et1_mut_p0_disabled, ["ET1-P0P1-DISABLED"], ()),
    ("E03-exit-code-conflict", et1_mut_exit_code_conflict, ["ET1-EXIT-CODE-CONFLICT"], ()),
    ("E04-unknown-evaluator", et1_mut_unknown_evaluator, ["ET1-UNKNOWN-EVALUATOR"], ()),
    ("E05-negative-control-removed", et1_mut_negative_control_removed, ["ET1-MISSING-NEGATIVE-CONTROL"], ()),
    ("E06-p0p1-unreferenced", et1_mut_p0p1_unreferenced, ["ET1-P0P1-UNREFERENCED"], ()),
    ("E07-profile-unknown-trap", et1_mut_profile_unknown_trap, ["ET1-PROFILE-UNKNOWN-TRAP"], ()),
    ("E08-registry-unreadable", et1_mut_registry_unreadable, ["ET1-REGISTRY-ERROR"], ()),
    ("E09-profiles-missing", et1_mut_profiles_missing, ["ET1-PROFILES-ERROR"], ()),
    ("E10-second-trap-deleted", et1_mut_second_trap_deleted, ["ET1-TRAP-DELETED"], ()),
    ("E11-shell-command-in-registry", et1_mut_shell_command_in_registry, ["SCHEMA-ADDITIONAL"], ()),
    ("E12-risk-enum-violation", et1_mut_risk_downgrade_p0_to_p3, ["SCHEMA-ENUM"], ()),
    ("E13-exit-code-zero", et1_mut_exit_code_zero, ["SCHEMA-ENUM"], ()),
    ("E14-stop-phase-weakened", et1_mut_stop_phase_weakened, ["SCHEMA-ENUM"], ()),
]

ET1_GREEN_CONTROLS = [
    ("EC01-pristine-registry-green", et1_control_pristine),
    ("EC02-traps-renumbered-uniquely", et1_control_trap_renumbered_consistently),
    ("EC03-profile-extended", et1_control_profile_extended),
    ("EC04-new-p2-trap-added", et1_control_trap_added),
]
