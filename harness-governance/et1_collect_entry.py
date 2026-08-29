"""HE2-ET1-R3 collect-child plugin entry shim.

The R3 contract requires the collect child to run with CWD == the
repository's canonical backend/ directory (the same CWD the authority
command uses). From there, the old import name `tests.pytest_et1_collector`
collides with the product's `backend/tests` package, so pytest loads THIS
uniquely-named entry module instead (`-p et1_collect_entry`, resolved from
PYTHONPATH=harness-governance) and this shim executes the runner-owned
plugin file into this module namespace via runpy — the plugin's own bytes,
its own __file__, its own hooks. Nothing about the plugin is duplicated.

The plugin file location is provided by the runner via
ET1_RUNNER_PLUGIN_FILE (absolute). Fail closed when absent.
"""

import os
import runpy

_plugin_file = os.environ.get("ET1_RUNNER_PLUGIN_FILE", "")
if not _plugin_file:
    raise SystemExit("et1_collect_entry: ET1_RUNNER_PLUGIN_FILE missing")

# run_path returns the executed namespace; the hooks must land in THIS
# module's globals for pytest's -p registration to see them.
globals().update(runpy.run_path(_plugin_file, run_name=__name__))
