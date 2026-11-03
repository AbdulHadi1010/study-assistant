"""Starter checks: generated files compile, and only LIVE blocks differ from the solution."""
import py_compile
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import make_starter  # noqa: E402

EXPECTED_LIVE = {"save_course", "grade_needed", "add_task", "list_tasks", "break_down_project", "routes", "ask_agent"}


def build(tmp_path):
    for folder in make_starter.SOURCE_DIRS:
        shutil.copytree(ROOT / folder, tmp_path / folder, ignore=shutil.ignore_patterns("__pycache__"))
    make_starter.make_starter(tmp_path)
    return tmp_path / "starter"


def test_starter_compiles_and_matches_markers(tmp_path):
    starter = build(tmp_path)
    found = set()
    for folder in make_starter.SOURCE_DIRS:
        for solution in (ROOT / folder).glob("*.py"):
            generated = (starter / folder / solution.name).read_text(encoding="utf-8")
            py_compile.compile(str(starter / folder / solution.name), doraise=True)
            solution_names = re.findall(r"# >>> LIVE: ([\w]+)", solution.read_text(encoding="utf-8"))
            todo_names = re.findall(r"# TODO \(live\): ([\w]+)", generated)
            assert solution_names == todo_names, solution.name
            assert "# >>> LIVE" not in generated
            found.update(solution_names)
    assert found == EXPECTED_LIVE


def test_nothing_else_differs(tmp_path):
    """Strip LIVE blocks from the solution and the TODO lines from the starter: the rest must be identical."""
    starter = build(tmp_path)
    for folder in make_starter.SOURCE_DIRS:
        for solution in (ROOT / folder).glob("*.py"):
            without_live = re.sub(r"[ \t]*# >>> LIVE:.*?# <<< LIVE:[^\n]*\n", "", solution.read_text(encoding="utf-8"), flags=re.S)
            generated = (starter / folder / solution.name).read_text(encoding="utf-8")
            without_todo = re.sub(r"[ \t]*# TODO \(live\):[^\n]*\n(?:[ \t]*# Hint:[^\n]*\n)?[ \t]*raise NotImplementedError[^\n]*\n", "", generated)
            assert without_live == without_todo, solution.name
