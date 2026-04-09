"""
Scans /codeload/moonshot/ for Moonshot strategy definitions.

QR's moonshot service only loads strategies from /codeload/moonshot/ (it must
be a Python package with __init__.py). Strategies placed elsewhere under
/codeload are not discoverable by QR and cannot be backtested or traded.

Uses Python's ast module to parse .py files without importing them, so no
side effects or dependency on the moonshot package being installed.

Each Moonshot strategy class is identified by:
  - Having a CODE = "<string>" class-level attribute
  - Being a class definition (subclass of anything — we don't trace inheritance)

The scan skips:
  - .ipynb_checkpoints/  (Jupyter auto-save folders)
  - .quantrocket/        (QR internal files and templates)
  - .moonshot_tmp/       (QR internal temp directory)
  - __pycache__/
"""

import ast
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Directories to skip during the walk (matched against each path component)
_SKIP_DIRS = {
    ".ipynb_checkpoints",
    ".quantrocket",
    ".moonshot_tmp",
    "__pycache__",
    ".git",
}


def _camel_to_title(name: str) -> str:
    """Convert CamelCase class name to human-readable title. e.g. UpMinusDown → Up Minus Down."""
    spaced = re.sub(r"([A-Z][a-z]+)", r" \1", re.sub(r"([A-Z]+)(?=[A-Z][a-z])", r"\1 ", name))
    return spaced.strip().title()


def _extract_strategies_from_file(path: Path) -> list[dict]:
    """
    Parse a single .py file with ast and return a list of strategy dicts for
    every class that has a CODE = "<literal string>" attribute.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        logger.debug("Skipping %s: syntax error (%s)", path, exc)
        return []
    except Exception as exc:
        logger.debug("Skipping %s: could not parse (%s)", path, exc)
        return []

    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        code_value: str | None = None
        docstring: str = ""

        for item in node.body:
            # Look for CODE = "<string>" as a class-level assignment
            if (
                isinstance(item, ast.Assign)
                and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
                and item.targets[0].id == "CODE"
                and isinstance(item.value, ast.Constant)
                and isinstance(item.value.value, str)
            ):
                code_value = item.value.value
                break

        if code_value is None:
            continue

        # Extract docstring if present
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            # Collapse whitespace in the docstring for storage
            docstring = " ".join(node.body[0].value.value.split())

        results.append({
            "strategy_id": code_value,
            "name": _camel_to_title(node.name),
            "description": docstring,
            "category": "Moonshot",
            "source": "quantrocket",
        })

    return results


def scan_codeload(codeload_path: str | None = None) -> list[dict]:
    """
    Walk the codeload directory and return a list of strategy dicts for every
    Moonshot strategy class found.

    codeload_path defaults to the CODELOAD_PATH env var, then /codeload.
    """
    base = Path(codeload_path or os.environ.get("CODELOAD_PATH", "/codeload"))
    root = base / "moonshot"

    if not root.exists():
        logger.warning("Codeload path %s does not exist; no QR strategies found", root)
        return []

    discovered: dict[str, dict] = {}  # de-duplicate by strategy_id

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            filepath = Path(dirpath) / filename
            for strat in _extract_strategies_from_file(filepath):
                sid = strat["strategy_id"]
                if sid in discovered:
                    logger.debug(
                        "Duplicate CODE '%s' found in %s (already seen); keeping first",
                        sid, filepath,
                    )
                else:
                    discovered[sid] = strat
                    logger.debug("Found strategy '%s' (%s) in %s", sid, strat["name"], filepath)

    logger.info("QR strategy scan of %s found %d strategies", root, len(discovered))
    return list(discovered.values())
