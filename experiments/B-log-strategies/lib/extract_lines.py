#!/usr/bin/env python3
"""
B-log-strategies/lib/extract_lines.py

Convert a Loki CSV (columns: timestamp_ns, pod, container, app, line)
into a plain-text log file suitable for LogShrink and Denum.

Lines are sorted by timestamp_ns.  ANSI escape codes and blank lines
are stripped.
"""

import argparse
import csv
import re
from pathlib import Path

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mABCDEFGHJKSTfnihlp]')


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    in_path  = Path(args.csv)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    with open(in_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts   = int(row.get("timestamp_ns", 0))
            line = strip_ansi(row.get("line", "")).strip()
            if line:
                rows.append((ts, line))

    rows.sort(key=lambda r: r[0])

    with open(out_path, "w", encoding="utf-8") as f:
        for _, line in rows:
            f.write(f"{line}\n")

    print(f"[extract_lines] {len(rows)} lines → {out_path}")


if __name__ == "__main__":
    main()
