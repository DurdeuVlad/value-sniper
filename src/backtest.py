"""
Backtesting module for Value Sniper.

Runs the sniper at historical monthly dates and checks whether predicted
support levels were actually hit (intraday Low <= level) within a forward
window of N trading days.
"""

import argparse
import os
import sys
import csv
from dataclasses import dataclass, fields
from datetime import timedelta

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))
from sniper import TechSniperAI


@dataclass
class BacktestResult:
    ticker: str
    analysis_date: str
    price_at_analysis: float
    level_1_price: float
    level_2_price: float
    level_3_price: float
    l1_pct_drop: float
    l2_pct_drop: float
    l3_pct_drop: float
    l1_hit: bool
    l2_hit: bool
    l3_hit: bool
    l1_days_to_hit: int | None
    l2_days_to_hit: int | None
    l3_days_to_hit: int | None
    max_drawdown_pct: float
    notes: str


def generate_monthly_dates(start: str, end: str) -> list[str]:
    """First trading day of each month between start and end (inclusive)."""
    dates = []
    current = pd.Timestamp(start).replace(day=1)
    end_ts = pd.Timestamp(end)
    while current <= end_ts:
        # Move to first weekday of the month (Mon=0..Fri=4)
        day = current
        while day.weekday() > 4:
            day += timedelta(days=1)
        if day <= end_ts:
            dates.append(day.strftime('%Y-%m-%d'))
        # Next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return dates


def _days_to_hit(lows: pd.Series, level: float) -> int | None:
    """Return number of days until Low <= level, or None if never hit."""
    hits = lows[lows <= level]
    if hits.empty:
        return None
    return int((hits.index[0] - lows.index[0]).days)


class Backtester:
    def __init__(self, ticker: str, forward_days: int = 60, verbose: bool = True):
        self.ticker = ticker.upper()
        self.forward_days = forward_days
        self.verbose = verbose

    def _fetch_forward_data(self, start_date: str) -> pd.DataFrame:
        end = (pd.Timestamp(start_date) + timedelta(days=self.forward_days + 30)).strftime('%Y-%m-%d')
        df = yf.download(self.ticker, start=start_date, end=end, interval='1d', progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # Exclude the analysis date itself — forward window starts day after
        if not df.empty:
            df = df.iloc[1:]
        return df.head(self.forward_days)

    def run_single(self, date: str) -> BacktestResult | None:
        notes = []
        try:
            bot = TechSniperAI(self.ticker, as_of_date=date, use_cache=True)
            if bot.current_price == 0:
                return None
            orders = bot.generate_orders()
            if not orders:
                return None
        except Exception as e:
            if self.verbose:
                print(f"  [ERROR] {date}: {e}")
            return None

        level_prices = [v['price'] for v in orders.values()]
        level_prices.sort(reverse=True)
        while len(level_prices) < 3:
            level_prices.append(level_prices[-1] * 0.95)

        l1, l2, l3 = level_prices[0], level_prices[1], level_prices[2]
        price = bot.current_price

        if 'Protocol C - Options' in bot.runtime_log and 'Skipped' in bot.runtime_log['Protocol C - Options']:
            notes.append("options skipped")

        # Fetch forward price data
        fwd = self._fetch_forward_data(date)
        if fwd.empty:
            notes.append("no forward data")
            return BacktestResult(
                ticker=self.ticker, analysis_date=date,
                price_at_analysis=round(price, 2),
                level_1_price=round(l1, 2), level_2_price=round(l2, 2), level_3_price=round(l3, 2),
                l1_pct_drop=round((price - l1) / price * 100, 2),
                l2_pct_drop=round((price - l2) / price * 100, 2),
                l3_pct_drop=round((price - l3) / price * 100, 2),
                l1_hit=False, l2_hit=False, l3_hit=False,
                l1_days_to_hit=None, l2_days_to_hit=None, l3_days_to_hit=None,
                max_drawdown_pct=0.0, notes=', '.join(notes)
            )

        lows = fwd['Low']
        l1_days = _days_to_hit(lows, l1)
        l2_days = _days_to_hit(lows, l2)
        l3_days = _days_to_hit(lows, l3)

        actual_min_low = float(lows.min())
        max_drawdown_pct = round((price - actual_min_low) / price * 100, 2)

        result = BacktestResult(
            ticker=self.ticker, analysis_date=date,
            price_at_analysis=round(price, 2),
            level_1_price=round(l1, 2), level_2_price=round(l2, 2), level_3_price=round(l3, 2),
            l1_pct_drop=round((price - l1) / price * 100, 2),
            l2_pct_drop=round((price - l2) / price * 100, 2),
            l3_pct_drop=round((price - l3) / price * 100, 2),
            l1_hit=l1_days is not None,
            l2_hit=l2_days is not None,
            l3_hit=l3_days is not None,
            l1_days_to_hit=l1_days,
            l2_days_to_hit=l2_days,
            l3_days_to_hit=l3_days,
            max_drawdown_pct=max_drawdown_pct,
            notes=', '.join(notes) if notes else 'ok'
        )

        if self.verbose:
            hits = f"L1={'HIT' if result.l1_hit else 'miss'} L2={'HIT' if result.l2_hit else 'miss'} L3={'HIT' if result.l3_hit else 'miss'}"
            print(f"  {date} | price=${price:.2f} | L1=${l1:.2f} L2=${l2:.2f} L3=${l3:.2f} | {hits} | drawdown={max_drawdown_pct:.1f}%")

        return result

    def run(self, dates: list[str]) -> list[BacktestResult]:
        print(f"\n=== BACKTESTING {self.ticker} — {len(dates)} dates, {self.forward_days}-day window ===\n")
        results = []
        for date in dates:
            r = self.run_single(date)
            if r:
                results.append(r)
        return results

    @staticmethod
    def summarize(results: list[BacktestResult]) -> dict:
        n = len(results)
        if n == 0:
            return {}
        l1_hits = [r for r in results if r.l1_hit]
        l2_hits = [r for r in results if r.l2_hit]
        l3_hits = [r for r in results if r.l3_hit]
        avg_days = lambda hits: round(np.mean([r.l1_days_to_hit for r in hits]), 1) if hits else None

        return {
            'total_dates': n,
            'l1_hit_rate': f"{len(l1_hits)}/{n} ({len(l1_hits)/n*100:.0f}%)",
            'l2_hit_rate': f"{len(l2_hits)}/{n} ({len(l2_hits)/n*100:.0f}%)",
            'l3_hit_rate': f"{len(l3_hits)}/{n} ({len(l3_hits)/n*100:.0f}%)",
            'l1_avg_days': avg_days(l1_hits),
            'l2_avg_days': round(np.mean([r.l2_days_to_hit for r in l2_hits]), 1) if l2_hits else None,
            'l3_avg_days': round(np.mean([r.l3_days_to_hit for r in l3_hits]), 1) if l3_hits else None,
            'avg_max_drawdown': f"{np.mean([r.max_drawdown_pct for r in results]):.1f}%",
        }

    @staticmethod
    def export_csv(results: list[BacktestResult], path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[field.name for field in fields(BacktestResult)])
            writer.writeheader()
            for r in results:
                writer.writerow({field.name: getattr(r, field.name) for field in fields(r)})
        print(f"\nExported to: {path}")


def _print_summary(summary: dict):
    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Value Sniper Backtester')
    parser.add_argument('ticker', type=str, help='Stock ticker (e.g. MSFT)')
    parser.add_argument('--date', type=str, default=None, help='Single historical date (YYYY-MM-DD)')
    parser.add_argument('--start', type=str, default=None, help='Backtest range start (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None, help='Backtest range end (YYYY-MM-DD, default: today)')
    parser.add_argument('--forward', type=int, default=60, help='Forward window in days (default: 60)')
    args = parser.parse_args()

    bt = Backtester(args.ticker, forward_days=args.forward)

    if args.date:
        result = bt.run_single(args.date)
        if result:
            _print_summary(bt.summarize([result]))
    elif args.start:
        end = args.end or pd.Timestamp.now().strftime('%Y-%m-%d')
        dates = generate_monthly_dates(args.start, end)
        results = bt.run(dates)
        if results:
            _print_summary(bt.summarize(results))
            start_str = args.start.replace('-', '')
            end_str = end.replace('-', '')
            out_path = os.path.join(
                os.path.dirname(__file__), '..', '_runtime',
                f"{args.ticker}_backtest_{start_str}_{end_str}.csv"
            )
            bt.export_csv(results, os.path.normpath(out_path))
    else:
        parser.error("Provide --date or --start")
