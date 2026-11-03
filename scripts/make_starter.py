"""Generate starter/ from the finished solution (run on the `solution` branch).

Copies lambda/, app/ and agent/ into starter/ and replaces every block between
`# >>> LIVE: <name>` and `# <<< LIVE: <name>` with a TODO and a
NotImplementedError. The `master` branch is this starter: during the workshop
each blank is filled in by copying the finished file from the `solution` branch.
Markers may carry a hint: `# >>> LIVE: grade_needed | hint: earned vs remaining weight`.
Re-running overwrites starter/ (it is generated; do not edit it by hand).
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = ["lambda", "app", "agent"]
START = re.compile(r"^(\s*)# >>> LIVE: (?P<name>[^|\n]+?)\s*(?:\|\s*hint:\s*(?P<hint>.*?))?\s*$")
END = re.compile(r"^\s*# <<< LIVE: (?P<name>.+?)\s*$")


def replace_live_blocks(text: str, filename: str = "") -> str:
    """Return text with each LIVE block swapped for a TODO placeholder."""
    output, lines = [], iter(text.splitlines())
    for line in lines:
        start = START.match(line)
        if not start:
            output.append(line)
            continue
        indent, name, hint = start.group(1), start.group("name"), start.group("hint")
        for inner in lines:  # skip the solution until the matching end marker
            end = END.match(inner)
            if end:
                if end.group("name") != name:
                    raise ValueError(f"{filename}: LIVE block '{name}' closed by '{end.group('name')}'")
                break
        else:
            raise ValueError(f"{filename}: LIVE block '{name}' is never closed")
        output.append(f"{indent}# TODO (live): {name}")
        if hint:
            output.append(f"{indent}# Hint: {hint}")
        output.append(f'{indent}raise NotImplementedError("{name} is filled in during the workshop: '
                      f'git checkout origin/solution -- {filename}")')
    return "\n".join(output) + "\n"


def make_starter(root: Path = ROOT) -> list[Path]:
    target = root / "starter"
    if target.exists():
        shutil.rmtree(target)
    written = []
    for folder in SOURCE_DIRS:
        for source in sorted((root / folder).glob("*.py")):
            destination = target / folder / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(replace_live_blocks(source.read_text(encoding="utf-8"), f"{folder}/{source.name}"),
                                   encoding="utf-8")
            written.append(destination)
        for data_file in sorted((root / folder).glob("*.json")):  # e.g. agent/functions.json: copied as is
            shutil.copy(data_file, target / folder / data_file.name)
            written.append(target / folder / data_file.name)
    return written


if __name__ == "__main__":
    files = make_starter()
    print(f"Wrote {len(files)} files to starter/")
