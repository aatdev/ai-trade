#!/usr/bin/env python3
"""
Reversal pattern scanner — Undercut & Rally / Double Bottom

Reads OHLCV from the local metrics cache (state/metrics/TICKER/ohlcv.json,
written by scripts/collect_russell.js) and detects PLTR-Apr-2026-style reversals
(mirror of reversal_hunter.pine):

  1) Undercut prior pivot low (≤ N% below) OR double bottom touch (±M%)
  2) Capitulation candle: volume ≥ K×SMA, lower wick ≥ X% of range,
     close in top Y% of range, range ≥ Z×ATR(14), RSI(14) ≤ T
  3) Bullish confirmation in next 1–2 bars: close > capitulation high
     (optional gap-up). Pattern is invalidated if low pierces cap low.

Designed for cron / launchd / loop execution.

Usage:
  python3 scripts/scan_reversals.py                       # scan all tickers
  python3 scripts/scan_reversals.py --ticker PLTR         # one ticker
  python3 scripts/scan_reversals.py --limit 200           # cap N tickers
  python3 scripts/scan_reversals.py --confirmed-only      # only confirmed
  python3 scripts/scan_reversals.py --scan-last-n 1       # only latest bar
  python3 scripts/scan_reversals.py --min-weight 0.05     # skip tiny weights
  python3 scripts/scan_reversals.py --interval 3600       # re-scan every 1h
  python3 scripts/scan_reversals.py --source snp500        # weight order from S&P 500

Cron example (daily at 22:30 ET):
  30 22 * * 1-5  cd /path/to/repo && /usr/bin/python3 scripts/scan_reversals.py >> logs/scan.log 2>&1

"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# The metrics cache reader lives in scripts/lib (shared with the screeners).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
import metrics_cache  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Universe files (same shapes scripts/collect_russell.js reads) — used only to
# rank tickers by index weight and honor --min-weight. Candles come from the cache.
UNIVERSE_FILES = {
    "russell": os.path.join(REPO_ROOT, "state", "russel2000.json"),
    "snp500": os.path.join(REPO_ROOT, "state", "sp500.csv"),
    "sp500": os.path.join(REPO_ROOT, "state", "sp500.csv"),
}

# ─── Config ──────────────────────────────────────────────────────────────────


@dataclass
class Config:
    pivot_left: int = 10
    pivot_right: int = 5
    prior_low_max_age: int = 120
    max_undercut_pct: float = 4.0
    double_bottom_tol_pct: float = 2.0
    allow_double_bottom: bool = True
    vol_mult: float = 1.8
    vol_avg_len: int = 20
    min_wick_frac: float = 0.40
    min_close_top_frac: float = 0.40
    use_atr_filter: bool = True
    atr_len: int = 14
    atr_mult: float = 1.3
    use_rsi: bool = True
    rsi_len: int = 14
    rsi_oversold: float = 35.0
    confirm_bars: int = 2
    require_gap_up: bool = False
    require_break_high: bool = True


# ─── Local cache + universe ──────────────────────────────────────────────────


def _load_universe_weights(source: str) -> dict[str, dict]:
    """Map TICKER → {weight_pct, market_value, price} from a universe file.

    Used only to rank tickers and honor --min-weight; missing/unknown source
    yields an empty map (everything ranks at weight 0)."""
    path = UNIVERSE_FILES.get(source)
    if not path or not os.path.exists(path):
        return {}
    out: dict[str, dict] = {}
    if path.endswith(".json"):
        rows = json.load(open(path, encoding="utf-8"))
        for r in rows:
            sym = (r.get("Ticker") or "").strip()
            if not sym:
                continue
            out[sym] = {
                "weight_pct": _to_float(r.get("Weight (%)")),
                "market_value": _to_float(str(r.get("Market Value", "")).replace(",", "")),
                "price": _to_float(str(r.get("Price", "")).replace(",", "")),
            }
    else:  # Wikipedia S&P 500 CSV — has no weights
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                sym = (r.get("Symbol") or "").strip()
                if sym:
                    out[sym] = {"weight_pct": 0.0, "market_value": 0.0, "price": 0.0}
    return out


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def fetch_tickers(source: str, limit: int | None = None,
                  sort_by_weight: bool = True) -> list[dict]:
    """Tickers that have a cached ohlcv.json, enriched with universe weight.

    The cache directory is the source of truth for *what* to scan (only collected
    tickers have candles); the universe file only supplies ordering metadata."""
    weights = _load_universe_weights(source)
    metrics_dir = metrics_cache.METRICS_DIR
    rows: list[dict] = []
    if os.path.isdir(metrics_dir):
        for name in os.listdir(metrics_dir):
            if not os.path.exists(os.path.join(metrics_dir, name, "ohlcv.json")):
                continue
            m = metrics_cache.read_metrics(name) or {}
            sym = m.get("ticker") or name
            w = weights.get(sym, {})
            rows.append({
                "ticker": sym,
                "name": m.get("name", sym),
                "sector": m.get("sector"),
                "weight_pct": w.get("weight_pct", 0.0),
                "market_value": w.get("market_value", 0.0),
                "price": w.get("price", 0.0),
            })
    if sort_by_weight:
        rows.sort(key=lambda t: (-(t.get("weight_pct") or 0.0), t["ticker"]))
    return rows[:limit] if limit else rows


def fetch_candles(ticker: str, count: int = 200) -> list[dict]:
    """Last `count` daily bars (oldest-first) from state/metrics/TICKER/ohlcv.json."""
    doc = metrics_cache.read_ohlcv(ticker)
    bars = doc.get("bars") if doc else None
    if not bars:
        return []
    bars = bars[-count:] if count and len(bars) > count else bars
    return [
        {
            "time": b.get("time"),
            "date": b.get("date"),
            "open": b.get("open"),
            "high": b.get("high"),
            "low": b.get("low"),
            "close": b.get("close"),
            "volume": b.get("volume") or 0,
        }
        for b in bars
    ]


# ─── Indicators (Pine-equivalent) ────────────────────────────────────────────


def sma(values: list[float], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= length:
            s -= values[i - length]
        if i >= length - 1:
            out[i] = s / length
    return out


def true_range(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    tr = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    return tr


def atr_wilder(highs, lows, closes, length: int = 14) -> list[float | None]:
    tr = true_range(highs, lows, closes)
    atr: list[float | None] = [None] * len(tr)
    if len(tr) < length:
        return atr
    atr[length - 1] = sum(tr[:length]) / length
    for i in range(length, len(tr)):
        atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr


def rsi_wilder(closes: list[float], length: int = 14) -> list[float | None]:
    rsi: list[float | None] = [None] * len(closes)
    if len(closes) <= length:
        return rsi
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:length]) / length
    avg_l = sum(losses[:length]) / length
    rsi[length] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(length + 1, len(closes)):
        avg_g = (avg_g * (length - 1) + gains[i - 1]) / length
        avg_l = (avg_l * (length - 1) + losses[i - 1]) / length
        rsi[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return rsi


def find_pivot_lows(lows: list[float], left: int, right: int) -> list[tuple[int, float]]:
    """Strict pivot low: surrounded by strictly higher lows on both sides."""
    out = []
    n = len(lows)
    for i in range(left, n - right):
        v = lows[i]
        ok = True
        for j in range(i - left, i + right + 1):
            if j != i and lows[j] <= v:
                ok = False
                break
        if ok:
            out.append((i, v))
    return out


# ─── Pattern detection ───────────────────────────────────────────────────────


@dataclass
class Signal:
    ticker: str
    cap_date: str
    cap_low: float
    cap_high: float
    cap_close: float
    cap_volume: int
    vol_x_sma: float
    wick_frac: float
    close_top_frac: float
    rsi: float | None
    range_x_atr: float | None
    prior_low: float
    prior_low_date: str
    undercut_pct: float
    pattern_kind: str  # 'undercut' | 'double_bottom'
    confirmed: bool = False
    confirm_date: str | None = None
    confirm_close: float | None = None
    rebound_pct: float | None = None


def detect(ticker: str, bars: list[dict], cfg: Config, scan_last_n: int = 3) -> list[Signal]:
    min_bars = max(cfg.atr_len, cfg.rsi_len, cfg.vol_avg_len,
                   cfg.pivot_left + cfg.pivot_right) + 10
    if len(bars) < min_bars:
        return []

    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    vols = [float(b.get("volume") or 0) for b in bars]
    dates = [b["date"] for b in bars]

    vol_sma = sma(vols, cfg.vol_avg_len)
    atr = atr_wilder(highs, lows, closes, cfg.atr_len)
    rsi = rsi_wilder(closes, cfg.rsi_len)
    pivots = find_pivot_lows(lows, cfg.pivot_left, cfg.pivot_right)

    signals: list[Signal] = []
    n = len(bars)
    start = max(0, n - scan_last_n)

    for i in range(start, n):
        # Latest pivot low strictly older than i, within max_age
        prior = None
        for pi, pv in pivots:
            age = i - pi
            if age >= cfg.pivot_right + 2 and age <= cfg.prior_low_max_age:
                prior = (pi, pv)
        if prior is None:
            continue
        pidx, plow = prior

        rng = highs[i] - lows[i]
        if rng <= 0:
            continue
        wick = min(opens[i], closes[i]) - lows[i]
        wick_frac = wick / rng
        close_top_frac = (closes[i] - lows[i]) / rng

        is_undercut = plow * (1 - cfg.max_undercut_pct / 100) <= lows[i] < plow
        is_double = (cfg.allow_double_bottom and
                     abs(lows[i] - plow) <= plow * (cfg.double_bottom_tol_pct / 100))
        if not (is_undercut or is_double):
            continue

        if vol_sma[i] is None or vols[i] < vol_sma[i] * cfg.vol_mult:
            continue
        if wick_frac < cfg.min_wick_frac or close_top_frac < cfg.min_close_top_frac:
            continue
        if cfg.use_atr_filter and (atr[i] is None or rng < atr[i] * cfg.atr_mult):
            continue
        if cfg.use_rsi and (rsi[i] is None or rsi[i] > cfg.rsi_oversold):
            continue

        sig = Signal(
            ticker=ticker,
            cap_date=dates[i],
            cap_low=lows[i],
            cap_high=highs[i],
            cap_close=closes[i],
            cap_volume=int(vols[i]),
            vol_x_sma=round(vols[i] / vol_sma[i], 2),
            wick_frac=round(wick_frac, 2),
            close_top_frac=round(close_top_frac, 2),
            rsi=round(rsi[i], 1) if rsi[i] is not None else None,
            range_x_atr=round(rng / atr[i], 2) if atr[i] else None,
            prior_low=plow,
            prior_low_date=dates[pidx],
            undercut_pct=round((plow - lows[i]) / plow * 100, 2),
            pattern_kind="undercut" if is_undercut else "double_bottom",
        )

        # Confirmation in [i+1 .. i+confirm_bars]
        for j in range(i + 1, min(n, i + 1 + cfg.confirm_bars)):
            if lows[j] < lows[i]:
                break  # invalidated
            is_green = closes[j] > opens[j]
            is_gap_up = opens[j] > closes[j - 1]
            broke = closes[j] > highs[i]
            if (is_green and (not cfg.require_gap_up or is_gap_up)
                    and (not cfg.require_break_high or broke)):
                sig.confirmed = True
                sig.confirm_date = dates[j]
                sig.confirm_close = closes[j]
                sig.rebound_pct = round((closes[j] - lows[i]) / lows[i] * 100, 2)
                break

        signals.append(sig)

    return signals


# ─── Output ──────────────────────────────────────────────────────────────────


def write_outputs(out_dir: Path, ts: str, cfg: Config, n_tickers: int,
                  signals: list[dict], errors: list[dict]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"reversal_{ts}.json"
    md_path = out_dir / f"reversal_{ts}.md"

    confirmed_count = sum(1 for s in signals if s.get("confirmed"))

    with open(json_path, "w") as f:
        json.dump({
            "generated_at": ts,
            "config": asdict(cfg),
            "ticker_count": n_tickers,
            "signal_count": len(signals),
            "confirmed_count": confirmed_count,
            "signals": signals,
            "errors": errors,
        }, f, indent=2, default=str)

    lines = [
        f"# Reversal scan — {ts}",
        "",
        f"- Tickers scanned: **{n_tickers}**",
        f"- Signals: **{len(signals)}** (confirmed: **{confirmed_count}**)",
        f"- Errors: {len(errors)}",
        "",
        "## Config",
        "```json",
        json.dumps(asdict(cfg), indent=2),
        "```",
        "",
        "## Signals",
        "",
    ]
    if signals:
        lines += [
            "| # | Ticker | Sector | Cap date | Pattern | Cap low | Prior low | UC% | Vol× | Wick% | RSI | Confirmed | Rebound% | Last px |",
            "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|:---:|---:|---:|",
        ]
        for n, s in enumerate(signals, 1):
            conf = (f"✓ {s['confirm_date']}" if s.get("confirmed") else "—")
            lines.append(
                f"| {n} | **{s['ticker']}** | {s.get('sector') or '-'} | "
                f"{s['cap_date']} | {s['pattern_kind']} | "
                f"{s['cap_low']:.2f} | {s['prior_low']:.2f} | "
                f"{s['undercut_pct']:+.1f} | {s['vol_x_sma']:.2f} | "
                f"{int(s['wick_frac']*100)} | "
                f"{s['rsi']:.0f} | {conf} | "
                f"{s.get('rebound_pct') or 0:.1f} | "
                f"{s.get('last_price', 0):.2f} |"
            )
    else:
        lines.append("_No signals._")

    md_path.write_text("\n".join(lines))
    return json_path, md_path


# ─── Main ────────────────────────────────────────────────────────────────────


def run_once(args, cfg: Config) -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")

    if args.ticker:
        tickers = [{"ticker": args.ticker.upper(), "name": "", "sector": "",
                    "weight_pct": 0}]
    else:
        tickers = fetch_tickers(args.source, limit=args.limit)
        if args.min_weight > 0:
            tickers = [t for t in tickers if (t.get("weight_pct") or 0) >= args.min_weight]
        if not args.quiet:
            print(f"[{ts}] Loaded {len(tickers)} cached tickers (weights from {args.source})")

    all_signals: list[dict] = []
    errors: list[dict] = []

    for i, t in enumerate(tickers, 1):
        sym = t["ticker"]
        try:
            bars = fetch_candles(sym, args.bars)
            if len(bars) < 50:
                continue
            sigs = detect(sym, bars, cfg, scan_last_n=args.scan_last_n)
            for s in sigs:
                d = asdict(s)
                d["sector"] = t.get("sector")
                d["name"] = t.get("name")
                d["last_price"] = bars[-1]["close"]
                d["last_date"] = bars[-1]["date"]
                all_signals.append(d)
            if not args.quiet and (i % 50 == 0 or sigs):
                marker = " ★" if sigs else ""
                print(f"  [{i:4d}/{len(tickers)}] {sym:8s}{marker}")
        except Exception as e:
            errors.append({"ticker": sym, "error": str(e)})
            if not args.quiet:
                print(f"  [{i:4d}/{len(tickers)}] {sym:8s} ERR: {e}", file=sys.stderr)

    if args.confirmed_only:
        all_signals = [s for s in all_signals if s.get("confirmed")]

    all_signals.sort(key=lambda s: (
        not s.get("confirmed"),
        -(s.get("rebound_pct") or 0),
        -(s.get("vol_x_sma") or 0),
    ))

    out_dir = Path(args.out_dir)
    json_path, md_path = write_outputs(out_dir, ts, cfg, len(tickers),
                                       all_signals, errors)

    if not args.quiet:
        confirmed = sum(1 for s in all_signals if s.get("confirmed"))
        print(f"\n{'=' * 60}")
        print(f"Tickers scanned : {len(tickers)}")
        print(f"Signals total   : {len(all_signals)}  (confirmed: {confirmed})")
        print(f"Errors          : {len(errors)}")
        print(f"JSON  → {json_path}")
        print(f"MD    → {md_path}")
        if all_signals:
            print(f"\nTop {min(5, len(all_signals))}:")
            for s in all_signals[:5]:
                tag = "✓" if s.get("confirmed") else " "
                print(f"  {tag} {s['ticker']:6s}  {s['cap_date']}  "
                      f"low={s['cap_low']:.2f}  "
                      f"vol×{s['vol_x_sma']}  "
                      f"reb={s.get('rebound_pct') or 0:+.1f}%")
    return len(all_signals)


def main():
    ap = argparse.ArgumentParser(
        description="Reversal pattern scanner (local metrics cache)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--limit", type=int, help="Cap on number of tickers")
    ap.add_argument("--ticker", help="Scan only one ticker")
    ap.add_argument("--source", default="russell", choices=["russell", "snp500", "sp500"],
                    help="Universe file for weight ordering / --min-weight (candles come from the cache)")
    ap.add_argument("--bars", type=int, default=200, help="Bars to load per ticker")
    ap.add_argument("--scan-last-n", type=int, default=3,
                    help="Bars at the right edge to test (1 = today only)")
    ap.add_argument("--confirmed-only", action="store_true")
    ap.add_argument("--out-dir", default="./results/scans")
    ap.add_argument("--min-weight", type=float, default=0.0,
                    help="Skip tickers with weight_pct below this")
    ap.add_argument("--interval", type=int, default=0,
                    help="If >0, re-run every N seconds")
    ap.add_argument("--quiet", action="store_true")

    # Tunables (override Config defaults)
    ap.add_argument("--vol-mult", type=float)
    ap.add_argument("--rsi-oversold", type=float)
    ap.add_argument("--max-undercut-pct", type=float)
    ap.add_argument("--require-gap-up", action="store_true")
    ap.add_argument("--no-rsi", action="store_true")
    ap.add_argument("--no-atr", action="store_true")

    args = ap.parse_args()

    cfg = Config()
    if args.vol_mult is not None: cfg.vol_mult = args.vol_mult
    if args.rsi_oversold is not None: cfg.rsi_oversold = args.rsi_oversold
    if args.max_undercut_pct is not None: cfg.max_undercut_pct = args.max_undercut_pct
    if args.require_gap_up: cfg.require_gap_up = True
    if args.no_rsi: cfg.use_rsi = False
    if args.no_atr: cfg.use_atr_filter = False

    if args.interval and args.interval > 0:
        if not args.quiet:
            print(f"Loop mode: every {args.interval}s. Ctrl-C to stop.")
        try:
            while True:
                t0 = time.time()
                run_once(args, cfg)
                elapsed = time.time() - t0
                sleep_for = max(1, args.interval - int(elapsed))
                if not args.quiet:
                    print(f"\nSleeping {sleep_for}s...\n")
                time.sleep(sleep_for)
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0
    else:
        run_once(args, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
