"""Command-line entry point for the Python turtle backtest."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

try:
    from .turtle_backtest import (
        Parameters,
        load_csv,
        load_raw_data_xlsx,
        run_backtest,
        safe_filename,
        select_instrument,
        write_results_csv,
    )
except ImportError:  # ``python run_backtest.py ...``
    from turtle_backtest import (
        Parameters,
        load_csv,
        load_raw_data_xlsx,
        run_backtest,
        safe_filename,
        select_instrument,
        write_results_csv,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Python版海龟回测")
    parser.add_argument("input", type=Path, help="行情 CSV，或 Raw_data xlsx")
    parser.add_argument("-o", "--output", type=Path, default=Path("backtest.csv"))
    parser.add_argument("--symbol", help="Raw_data 中要回测的代码或名称")
    parser.add_argument("--all", action="store_true", help="回测所有标的")
    parser.add_argument(
        "--list-symbols", action="store_true", help="列出所有可用标的"
    )
    parser.add_argument("--atr-period", type=int, default=20)
    parser.add_argument("--entry-period", type=int, default=20)
    parser.add_argument("--exit-period", type=int, default=10)
    parser.add_argument(
        "--warmup-bars",
        type=int,
        help="产生信号前要求的历史行情数；默认取ATR、入场和退出周期的最大值",
    )
    parser.add_argument("--risk", type=float, default=0.02)
    parser.add_argument("--buy-cost", type=float, default=0.0002)
    parser.add_argument("--sell-cost", type=float, default=0.0007)
    parser.add_argument("--initial-cash", type=float, default=1_000_000)
    args = parser.parse_args()

    parameters = Parameters(
        atr_period=args.atr_period,
        entry_period=args.entry_period,
        exit_period=args.exit_period,
        risk_fraction=args.risk,
        buy_cost_rate=args.buy_cost,
        sell_cost_rate=args.sell_cost,
        initial_cash=args.initial_cash,
        warmup_bars=args.warmup_bars,
    )

    if args.input.suffix.lower() not in {".xlsx", ".xlsm"}:
        rows, summary = run_backtest(load_csv(args.input), parameters)
        write_results_csv(rows, args.output)
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str))
        print(f"\n明细已写入: {args.output.resolve()}")
        return

    instruments = load_raw_data_xlsx(args.input)

    if args.list_symbols:
        for item in instruments:
            print(f"{item.symbol}\t{item.name}\t{len(item.bars):,} 行")
        return

    selected = (
        instruments
        if args.all
        else [select_instrument(instruments, args.symbol or "000300.SH")]
    )
    if len(selected) == 1:
        item = selected[0]
        rows, summary = run_backtest(item.bars, parameters)
        write_results_csv(rows, args.output)
        payload = {"name": item.name, "symbol": item.symbol, **asdict(summary)}
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        print(f"\n明细已写入: {args.output.resolve()}")
        return

    args.output.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    for item in selected:
        rows, summary = run_backtest(item.bars, parameters)
        detail_path = args.output / f"{safe_filename(item)}.csv"
        write_results_csv(rows, detail_path)
        summaries.append(
            {
                "name": item.name,
                "symbol": item.symbol,
                "observations": len(item.bars),
                **asdict(summary),
            }
        )
        print(f"完成 {item.name} ({item.symbol}) -> {detail_path}")

    summary_path = args.output / "summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8-sig") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"\n汇总已写入: {summary_path.resolve()}")


if __name__ == "__main__":
    main()
