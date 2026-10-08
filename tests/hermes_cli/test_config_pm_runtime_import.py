"""PM's minimal interpreter must not discover application provider plugins."""

import os
from pathlib import Path
import subprocess
import sys


def test_config_import_in_pm_runtime_skips_provider_plugin_discovery(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    runtime = tmp_path / "pm-runtime"
    runtime.mkdir()
    (runtime / "pm-runtime.json").write_text("{}", encoding="utf-8")
    home = tmp_path / "home"

    script = r"""
import importlib.abc
import pathlib
import sys

sys.prefix = sys.argv[1]

class BlockHttpx(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "httpx" or fullname.startswith("httpx."):
            raise ModuleNotFoundError("No module named 'httpx'", name=fullname)

sys.meta_path.insert(0, BlockHttpx())
sys.path.insert(0, sys.argv[2])
import hermes_cli.config
"""
    env = os.environ.copy()
    env["HERMES_HOME"] = str(home)
    result = subprocess.run(
        [sys.executable, "-c", script, str(runtime), str(repo_root)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Failed to load bundled provider plugin solstice" not in result.stderr
