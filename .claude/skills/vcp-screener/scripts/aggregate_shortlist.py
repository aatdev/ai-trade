#!/usr/bin/env python3
"""
Aggregate multiple VCP screener JSON reports into one ranked short-list.

Usage: python3 aggregate_shortlist.py report1.json report2.json ...
Dedupes by symbol (keeps the highest composite_score), sorts by execution-state
priority then score, and prints a compact actionable table.
"""
import json
import sys

STATE_ORDER = {
    "Pre-breakout": 0, "Breakout": 0, "Early-post-breakout": 1,
    "Extended": 2, "Overextended": 3, "Damaged": 4, "Invalid": 5,
}


def load(path):
    d = json.load(open(path))
    for v in d.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "symbol" in v[0]:
            return v
    return []


def main():
    best = {}
    for p in sys.argv[1:]:
        for c in load(p):
            s = c["symbol"]
            if s not in best or c.get("composite_score", 0) > best[s].get("composite_score", 0):
                best[s] = c

    cands = sorted(
        best.values(),
        key=lambda c: (STATE_ORDER.get(c.get("execution_state", ""), 9), -c.get("composite_score", 0)),
    )

    print(f"Объединено уникальных кандидатов: {len(cands)}\n")
    hdr = f"{'SYM':6}{'Scr':>5} {'State':<20}{'Piv%':>6} {'Contr':<14}{'RS':>4}{'Dry':>6}{'TT':>4}"
    print(hdr)
    print("-" * len(hdr))
    for c in cands:
        vcp = c.get("vcp_pattern", {}) or {}
        ctrs = vcp.get("contractions", []) or []
        cstr = ">".join(f"{ct.get('depth_pct', 0):.0f}" for ct in ctrs) if ctrs else "-"
        rs = (c.get("relative_strength", {}) or {}).get("rs_percentile", "-")
        dry = (c.get("volume_pattern", {}) or {}).get("dry_up_ratio", "-")
        tt = (c.get("trend_template", {}) or {}).get("score", "-")
        ttv = f"{tt:.0f}" if isinstance(tt, (int, float)) else "-"
        dryv = f"{dry:.2f}" if isinstance(dry, (int, float)) else "-"
        print(f"{c['symbol']:6}{c.get('composite_score', 0):>5.1f} "
              f"{c.get('execution_state', ''):<20}{c.get('distance_from_pivot_pct', 0):>6.1f} "
              f"{cstr:<14}{str(rs):>4}{dryv:>6}{ttv:>4}")


if __name__ == "__main__":
    main()
