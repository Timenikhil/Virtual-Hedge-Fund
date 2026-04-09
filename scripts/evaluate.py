"""
Evaluation script: run backtests across all portfolios and allocation methods,
then produce a comparison table and CSV for the FYP dissertation results section.

Usage:
    # Run equal_weight and score_weighted on all portfolios (no API calls):
    poetry run python scripts/evaluate.py

    # Also run ai_weighted with live Claude calls:
    poetry run python scripts/evaluate.py --live-ai

    # Specific portfolios / methods / date range:
    poetry run python scripts/evaluate.py \\
        --portfolio-ids 1,2 \\
        --methods equal_weight,score_weighted,ai_weighted \\
        --start-date 2025-01-02 \\
        --end-date 2025-12-31 \\
        --rebalance-days 21 \\
        --output-dir results/

Output:
    Prints a formatted table to stdout.
    Writes results/backtest_results.csv and results/backtest_summary.txt.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

METHODS_DEFAULT = ["equal_weight", "score_weighted"]
METHODS_WITH_AI = ["equal_weight", "score_weighted", "ai_weighted"]

COL_WIDTH = 16


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _herfindahl(weights: list[float]) -> float:
    """Herfindahl-Hirschman Index: sum of squared weights. Range [1/n, 1]."""
    return round(sum(w ** 2 for w in weights), 6)


def _fmt(value, decimals=2, suffix="") -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and not math.isfinite(value):
        return "—"
    return f"{value:.{decimals}f}{suffix}"


def _print_table(rows: list[dict], columns: list[tuple[str, str]]) -> None:
    """Print a simple fixed-width table. columns = [(key, header), ...]"""
    headers = [h for _, h in columns]
    keys = [k for k, _ in columns]

    sep = "  ".join("-" * COL_WIDTH for _ in columns)
    header_line = "  ".join(h.ljust(COL_WIDTH) for h in headers)

    print(sep)
    print(header_line)
    print(sep)
    for row in rows:
        line = "  ".join(str(row.get(k, "—")).ljust(COL_WIDTH) for k in keys)
        print(line)
    print(sep)


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def run_evaluation(
    portfolio_ids: list[int] | None,
    methods: list[str],
    start_date: str | None,
    end_date: str | None,
    rebalance_days: int,
    live_ai: bool,
    output_dir: Path,
) -> list[dict]:
    from vhf.db import connection
    from vhf.db.operations import get_db_portfolio_id, get_ranked_list
    from vhf.models.allocation import AllocationMethod
    from vhf.services.backtest import BacktestError, BacktestRequest, run_backtest

    connection.connect()

    # Resolve portfolio list
    if portfolio_ids:
        portfolios = []
        for pid in portfolio_ids:
            try:
                p = get_db_portfolio_id(pid)
                portfolios.append({"id": p.portfolio_id, "name": p.portfolio_name})
            except Exception as exc:
                print(f"  Warning: portfolio {pid} not found — {exc}", file=sys.stderr)
    else:
        all_p = get_ranked_list(None, None)
        portfolios = [{"id": p.portfolio_id, "name": p.portfolio_name} for p in all_p.portfolios]

    if not portfolios:
        print("No portfolios found. Run scripts/seed.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"\nEvaluating {len(portfolios)} portfolio(s) × {len(methods)} method(s)...\n")

    rows: list[dict] = []

    for portfolio in portfolios:
        pid = portfolio["id"]
        pname = portfolio["name"]

        for method_str in methods:
            try:
                method = AllocationMethod(method_str)
            except ValueError:
                print(f"  Unknown method '{method_str}', skipping.", file=sys.stderr)
                continue

            use_live_ai = live_ai and method == AllocationMethod.ai_weighted
            label = f"{pname} / {method_str}" + (" (live AI)" if use_live_ai else "")
            print(f"  Running {label} ...", end="", flush=True)

            try:
                result = run_backtest(BacktestRequest(
                    portfolio_id=pid,
                    method=method,
                    start_date=start_date or None,
                    end_date=end_date or None,
                    rebalance_frequency_days=rebalance_days,
                    live_ai_calls=use_live_ai,
                ))
            except BacktestError as exc:
                print(f" SKIPPED ({exc})")
                continue
            except Exception as exc:
                print(f" ERROR ({exc})")
                continue

            final_weights = [leg.final_weight for leg in result.strategy_legs]
            hhi = _herfindahl(final_weights)

            row = {
                "portfolio_id": pid,
                "portfolio": pname,
                "method": method_str,
                "live_ai": "yes" if use_live_ai else "no",
                "start_date": result.start_date,
                "end_date": result.end_date,
                "n_trading_days": result.n_trading_days,
                "n_rebalances": result.n_rebalances,
                "total_return_pct": result.total_return_pct,
                "annualised_return_pct": result.annualised_return_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown_pct": result.max_drawdown_pct,
                "hhi": hhi,                                   # concentration
                "ai_call_count": result.ai_call_count,
                "ai_fallback_count": result.ai_fallback_count,
                "weight_stability": result.weight_stability,
            }
            rows.append(row)

            summary = (
                f" return={_fmt(result.total_return_pct, suffix='%')}"
                f"  sharpe={_fmt(result.sharpe_ratio)}"
                f"  dd={_fmt(result.max_drawdown_pct, suffix='%')}"
            )
            if use_live_ai:
                summary += (
                    f"  ai_calls={result.ai_call_count}"
                    f"  fallbacks={result.ai_fallback_count}"
                    f"  stability={_fmt(result.weight_stability, 4)}"
                )
            print(summary)

    return rows


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "backtest_results.csv"
    if not rows:
        return path
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_summary(rows: list[dict], output_dir: Path, args: argparse.Namespace) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "backtest_summary.txt"

    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("VHF BACKTEST EVALUATION SUMMARY")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Rebalance frequency : {args.rebalance_days} trading days")
    lines.append(f"Date range          : {args.start_date or 'auto'} → {args.end_date or 'auto'}")
    lines.append(f"Live AI calls       : {'yes' if args.live_ai else 'no'}")
    lines.append("")

    # Group by portfolio
    portfolios = sorted({r["portfolio"] for r in rows})
    for pname in portfolios:
        lines.append(f"Portfolio: {pname}")
        lines.append("-" * 60)
        p_rows = [r for r in rows if r["portfolio"] == pname]

        for r in p_rows:
            lines.append(
                f"  {r['method']:20s}  "
                f"return={_fmt(r['total_return_pct'], suffix='%'):>10}  "
                f"sharpe={_fmt(r['sharpe_ratio']):>8}  "
                f"drawdown={_fmt(r['max_drawdown_pct'], suffix='%'):>10}  "
                f"HHI={_fmt(r['hhi'], 4):>8}"
            )
            if r.get("ai_call_count") is not None:
                lines.append(
                    f"    → AI calls={r['ai_call_count']}  "
                    f"fallbacks={r['ai_fallback_count']}  "
                    f"weight_stability={_fmt(r['weight_stability'], 4)}"
                )

        # Score deltas vs equal_weight baseline
        eq_row = next((r for r in p_rows if r["method"] == "equal_weight"), None)
        if eq_row and len(p_rows) > 1:
            lines.append("")
            lines.append("  vs equal_weight baseline:")
            for r in p_rows:
                if r["method"] == "equal_weight":
                    continue
                delta_ret = (
                    r["total_return_pct"] - eq_row["total_return_pct"]
                    if r["total_return_pct"] is not None and eq_row["total_return_pct"] is not None
                    else None
                )
                delta_sharpe = (
                    r["sharpe_ratio"] - eq_row["sharpe_ratio"]
                    if r["sharpe_ratio"] is not None and eq_row["sharpe_ratio"] is not None
                    else None
                )
                lines.append(
                    f"    {r['method']:20s}  "
                    f"Δreturn={_fmt(delta_ret, suffix='pp'):>10}  "
                    f"Δsharpe={_fmt(delta_sharpe, 3):>8}"
                )
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def print_results_table(rows: list[dict]) -> None:
    columns = [
        ("portfolio", "Portfolio"),
        ("method", "Method"),
        ("total_return_pct", "Return %"),
        ("annualised_return_pct", "Ann. Return %"),
        ("sharpe_ratio", "Sharpe"),
        ("max_drawdown_pct", "Max DD %"),
        ("hhi", "HHI"),
        ("n_rebalances", "Rebalances"),
    ]

    display_rows = []
    for r in rows:
        display_rows.append({
            "portfolio": r["portfolio"][:COL_WIDTH],
            "method": r["method"],
            "total_return_pct": _fmt(r["total_return_pct"], suffix="%"),
            "annualised_return_pct": _fmt(r["annualised_return_pct"], suffix="%"),
            "sharpe_ratio": _fmt(r["sharpe_ratio"]),
            "max_drawdown_pct": _fmt(r["max_drawdown_pct"], suffix="%"),
            "hhi": _fmt(r["hhi"], 4),
            "n_rebalances": r["n_rebalances"],
        })
    _print_table(display_rows, columns)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run comparative backtests across portfolios and allocation methods."
    )
    parser.add_argument(
        "--portfolio-ids",
        help="Comma-separated portfolio IDs (default: all)",
    )
    parser.add_argument(
        "--methods",
        default=",".join(METHODS_DEFAULT),
        help=f"Comma-separated methods (default: {','.join(METHODS_DEFAULT)})",
    )
    parser.add_argument(
        "--live-ai",
        action="store_true",
        help="Make live Claude API calls for ai_weighted (incurs cost).",
    )
    parser.add_argument("--start-date", help="ISO start date (default: earliest available)")
    parser.add_argument("--end-date", help="ISO end date (default: latest available)")
    parser.add_argument(
        "--rebalance-days",
        type=int,
        default=21,
        help="Rebalance frequency in trading days (default: 21 ≈ monthly)",
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Directory for CSV and summary output (default: results/)",
    )
    args = parser.parse_args()

    portfolio_ids: list[int] | None = None
    if args.portfolio_ids:
        try:
            portfolio_ids = [int(x.strip()) for x in args.portfolio_ids.split(",")]
        except ValueError:
            print("Error: --portfolio-ids must be comma-separated integers.", file=sys.stderr)
            sys.exit(1)

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    if args.live_ai and "ai_weighted" not in methods:
        methods.append("ai_weighted")

    output_dir = Path(args.output_dir)

    rows = run_evaluation(
        portfolio_ids=portfolio_ids,
        methods=methods,
        start_date=args.start_date,
        end_date=args.end_date,
        rebalance_days=args.rebalance_days,
        live_ai=args.live_ai,
        output_dir=output_dir,
    )

    if not rows:
        print("\nNo results produced.", file=sys.stderr)
        sys.exit(1)

    print("\n--- Results ---\n")
    print_results_table(rows)

    csv_path = write_csv(rows, output_dir)
    summary_path = write_summary(rows, output_dir, args)

    print(f"\nCSV   → {csv_path}")
    print(f"Summary → {summary_path}")


if __name__ == "__main__":
    main()
