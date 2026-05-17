#!/usr/bin/env python3
"""
B-log-strategies/lib/extract_lines.py

Convert a Loki CSV (columns: timestamp_ns, pod, container, app, line)
into a plain-text log file suitable for LogShrink and Denum.

Lines are sorted by timestamp_ns.  ANSI escape codes and blank lines
are stripped.

Corpus definition: Open5GS NFs + UERANSIM (simulated RAN/UE).
MongoDB (JSON structured logs, database infrastructure) and Beyla
(eBPF observability agent, meta-level) are excluded from all strategies
so that every strategy operates on the same input.
"""

import argparse
import csv
from pathlib import Path

from measure_overhead import strip_ansi

# Apps excluded from the corpus across all strategies.
EXCLUDE_APPS = {"mongodb", "beyla"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    in_path  = Path(args.csv)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    skipped = 0
    with open(in_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("app", "") in EXCLUDE_APPS:
                skipped += 1
                continue
            ts   = int(row.get("timestamp_ns", 0))
            line = strip_ansi(row.get("line", "")).strip()
            if line:
                rows.append((ts, line))

    if skipped:
        print(f"[extract_lines] skipped {skipped} lines from non-NF apps {sorted(EXCLUDE_APPS)}")

    rows.sort(key=lambda r: r[0])

    with open(out_path, "w", encoding="utf-8") as f:
        for _, line in rows:
            f.write(f"{line}\n")

    print(f"[extract_lines] {len(rows)} lines → {out_path}")


if __name__ == "__main__":
    main()
