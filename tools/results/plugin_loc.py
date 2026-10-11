"""
Plugin size and "what else changed" evidence for the modularity claim
(Results use case 5 / Table III).

    python tools/results/plugin_loc.py

Prints, for every device and control plugin:
  - lines of code in plugin.py (non-blank, non-comment) and the manifest
  - the commit that first added the plugin, and which files OUTSIDE the
    plugin's own folder that commit also changed (core / SDK / frontend)
plus the total size of the core backend, SDK and frontend for comparison.

Note: a commit that bundles unrelated work will list those files too -
read the list before claiming "zero core changes".
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _loc(path: Path) -> int:
    count = 0
    in_docstring = False
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if path.suffix == ".py":
            quotes = line.count('"""') + line.count("'''")
            if in_docstring:
                if quotes % 2 == 1:
                    in_docstring = False
                continue
            if line.startswith(('"""', "'''")) and quotes % 2 == 1:
                in_docstring = True
                continue
            if not line or line.startswith("#"):
                continue
        elif not line or line.startswith(("//", "/*", "*")):
            continue
        count += 1
    return count


def _tree_loc(root: Path, suffixes: tuple[str, ...]) -> int:
    return sum(
        _loc(p) for p in root.rglob("*")
        if p.suffix in suffixes and "node_modules" not in p.parts and "__pycache__" not in p.parts
    )


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=False
    ).stdout.strip()


def _adding_commit(folder: Path) -> tuple[str, list[str]]:
    rel = folder.relative_to(REPO).as_posix()
    # --follow so a later folder move/rename isn't mistaken for the original add
    commits = _git(
        "log", "--follow", "--diff-filter=A", "--format=%h", "--", f"{rel}/plugin.py"
    ).split()
    if not commits:
        return "uncommitted", []
    commit = commits[-1]  # oldest commit that added plugin.py
    changed = _git("show", "--name-only", "--format=", commit).splitlines()
    # The plugin's own files, wherever the folder lived at the time.
    own_prefix = _git(
        "show", "--name-only", "--format=", "--diff-filter=A", commit
    ).splitlines()
    own_dirs = {
        f.rsplit("/", 1)[0] + "/" for f in own_prefix
        if f.endswith("/plugin.py") and f.rsplit("/", 2)[-2] == folder.name
    }
    others = [
        f for f in changed
        if f
        and not any(f.startswith(d) for d in own_dirs)
        and not f.startswith(f"{rel}/")
        and not f.endswith(("CLAUDE.md", ".pyc"))
    ]
    return commit, others


def main() -> None:
    for kind in ("device", "control"):
        print(f"\n{kind.upper()} PLUGINS")
        for folder in sorted((REPO / "plugins" / kind).iterdir()):
            plugin = folder / "plugin.py"
            if not plugin.exists():
                continue
            manifest = folder / "manifest.json"
            commit, others = _adding_commit(folder)
            print(
                f"  {folder.name:<16} plugin.py {_loc(plugin):>5} lines"
                f"   manifest {(_loc(manifest) if manifest.exists() else 0):>4} lines"
                f"   added in {commit}"
            )
            for f in others:
                print(f"      also changed: {f}")

    print("\nFOR COMPARISON")
    print(f"  core backend (apps/backend/henosync)  {_tree_loc(REPO / 'apps/backend/henosync', ('.py',)):>6} lines")
    print(f"  plugin SDK (packages/plugin-sdk)       {_tree_loc(REPO / 'packages/plugin-sdk', ('.py',)):>6} lines")
    print(f"  frontend (apps/desktop/src)           {_tree_loc(REPO / 'apps/desktop/src', ('.ts', '.tsx')):>6} lines")


if __name__ == "__main__":
    main()
