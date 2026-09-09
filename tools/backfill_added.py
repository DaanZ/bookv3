"""Give every book the date it was added, taken from git.

`meta.addedAt` did not exist until the shelf needed to sort by it, so the 270 books
already on the shelf have no answer to when they arrived. Three sources were possible
and only one of them is true:

- **File timestamps are worthless here.** Restoring the library from git rewrote every
  file, so 254 of 270 share one mtime — the day of the restore, not the day of the book.
- **The pipeline does not record it.** Nothing downstream ever asked, so nothing upstream
  ever wrote it.
- **Git does know.** The commit that first added a book's JSON is the day it entered the
  library, and that history survives: 213 books on 2024-12-28, 41 on 2025-01-17, the rest
  this month.

One wrinkle: finishing a book *moves* its JSON from `books/available` to `books/read`, and
git records the arrival at the new path as an add. Taking the **earliest** date across
every path a stem has ever occupied keeps a finished book's original date instead of
re-dating it to the day it was finished.

Run once. `jobs.py` writes `addedAt` for everything ingested after this.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = ("books/available", "books/read")


def git_add_dates() -> dict[str, str]:
    """stem -> earliest ISO date at which any path for that stem was added."""
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--name-only", "--format=@%aI",
         "--reverse", "--", "books/"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout

    earliest: dict[str, str] = {}
    stamp = None
    for line in out.splitlines():
        if line.startswith("@"):
            stamp = line[1:]
        elif line.endswith(".json") and stamp:
            stem = os.path.basename(line)[:-5]
            if stem not in earliest or stamp < earliest[stem]:
                earliest[stem] = stamp
    return earliest


def main() -> int:
    dates = git_add_dates()
    written = missing = already = 0

    for folder in FOLDERS:
        path = os.path.join(ROOT, folder)
        if not os.path.isdir(path):
            continue
        for name in sorted(os.listdir(path)):
            if not name.endswith(".json"):
                continue
            stem = name[:-5]
            full = os.path.join(path, name)
            with open(full, encoding="utf-8") as handle:
                data = json.load(handle)
            meta = data.setdefault("meta", {})

            if meta.get("addedAt"):
                already += 1
                continue
            when = dates.get(stem)
            if not when:
                # Never committed — added since the last commit, so today is honest.
                missing += 1
                continue

            meta["addedAt"] = when
            meta["addedFrom"] = "git"
            with open(full, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=4)
            written += 1

    print(f"dated {written}, already had one {already}, no commit yet {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
