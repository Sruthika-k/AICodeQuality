"""Persistent test: replay_plateau.py imports nothing from LLM/Gemini libraries."""

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPLAY_SCRIPT = PROJECT_ROOT / "scripts" / "replay_plateau.py"


def test_replay_script_has_no_llm_imports():
    """Verify replay_plateau.py does not import from llm_interface or Gemini libraries."""
    if not REPLAY_SCRIPT.exists():
        raise FileNotFoundError(f"Replay script not found: {REPLAY_SCRIPT}")

    source = REPLAY_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])

    forbidden = {"llm_interface", "gemini", "google"}
    found = imports & forbidden

    assert not found, f"replay_plateau.py imports forbidden modules: {found}"
