"""
analysis/RQ2/run_all_analysis.py

Master runner for all RQ2 analysis modules.

Outputs land in:
    analysis/RQ2/figures/   (*.pdf)
    analysis/RQ2/tables/    (*.csv)
"""

import time
import traceback

import rq2a_volume_reduction
import rq2b_overhead
import rq2c_visibility
import rq2d_tradeoffs

MODULES = [
    ("RQ2a — Telemetry volume reduction",     rq2a_volume_reduction),
    ("RQ2b — Processing overhead",            rq2b_overhead),
    ("RQ2c — Retained visibility",            rq2c_visibility),
    ("RQ2d — Trade-off analysis (Pareto)",    rq2d_tradeoffs),
]


def main() -> None:
    from config import FIGURES_DIR, TABLES_DIR
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    total_start = time.perf_counter()
    results = []

    for label, module in MODULES:
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        t0 = time.perf_counter()
        status = "OK"
        try:
            module.run()
        except Exception:
            status = "FAILED"
            traceback.print_exc()
        elapsed = time.perf_counter() - t0
        results.append((label, elapsed, status))
        print(f"  → {status}  ({elapsed:.1f}s)")

    total = time.perf_counter() - total_start
    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    for label, elapsed, status in results:
        mark = "✓" if status == "OK" else "✗"
        print(f"  {mark}  {label:<44}  {elapsed:5.1f}s  {status}")
    print(f"\n  Total: {total:.1f}s")

    failed = [lbl for lbl, _, s in results if s != "OK"]
    if failed:
        print(f"\n  FAILED modules ({len(failed)}):")
        for lbl in failed:
            print(f"    - {lbl}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
