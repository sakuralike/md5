from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "rebuild_community_search_index.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location(
        "rebuild_community_search_index", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rebuild_script_requires_explicit_operation():
    module = _load_script_module()
    assert module.parse_args(["--dry-run", "--batch-size", "20"]).dry_run is True
    assert module.parse_args(["--apply", "--batch-size", "20"]).apply is True

def test_rebuild_script_accepts_bounded_resume_controls():
    module = _load_script_module()
    args = module.parse_args(
        [
            "--apply",
            "--batch-size",
            "20",
            "--max-batches",
            "3",
            "--resume-run-id",
            "synthetic-run-id",
        ]
    )
    assert args.max_batches == 3
    assert args.resume_run_id == "synthetic-run-id"
