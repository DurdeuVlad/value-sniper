"""
Value Sniper — Strategy Benchmark

Simulates the full compound trading cycle:
  1. Run sniper at start date → get 3 support levels
  2. Wait for price to hit the nearest level (entry)
  3. Wait for price to rise X% from entry (exit / take-profit)
  4. Re-run sniper from exit date → new levels
  5. Repeat until end of period

Tests 4 profit targets: +5%, +10%, +15%, +20%
Tests multiple tickers and start points.

Usage:
  python src/benchmark.py
  python src/benchmark.py --tickers MSFT AAPL NVDA --start 2023-01-01 --end 2026-01-01
  python src/benchmark.py --targets 5 10 15 20 --capital 10000
"""

import argparse
import os
import sys
import io
import csv
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule
from rich import box

console = Console(highlight=False, emoji=False)

# ─── data ─────────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    ticker: str
    strategy: str           # e.g. "+10%"
    start_date: str         # period start
    analysis_date: str      # date sniper was run
    entry_date: str
    entry_price: float
    entry_level: str        # L1 / L2 / L3
    exit_date: str
    exit_price: float
    pnl_pct: float
    hold_days: int
    target_hit: bool        # did it reach the profit target?
    open_position: bool     # position still open at period end


@dataclass
class StrategyResult:
    ticker: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    annualized_return_pct: float
    n_trades: int
    n_target_hits: int
    win_rate_pct: float
    avg_hold_days: float
    max_drawdown_pct: float
    trades: list


# ─── helpers ──────────────────────────────────────────────────────────────────

_OHLCV_CACHE: dict = {}

def _fetch_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    key = (ticker, start, end)
    if key in _OHLCV_CACHE:
        return _OHLCV_CACHE[key]
    df = yf.download(ticker, start=start, end=end, interval='1d', progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    _OHLCV_CACHE[key] = df
    return df


def _first_hit_low(df: pd.DataFrame, level: float, after_idx: int = 0) -> Optional[tuple]:
    """Return (date_str, row_index) of first day where Low <= level, starting at after_idx."""
    subset = df.iloc[after_idx:]
    hits = subset[subset['Low'] <= level]
    if hits.empty:
        return None
    idx = df.index.get_loc(hits.index[0])
    return hits.index[0].strftime('%Y-%m-%d'), idx


def _first_hit_high(df: pd.DataFrame, level: float, after_idx: int = 0) -> Optional[tuple]:
    """Return (date_str, row_index) of first day where High >= level, starting at after_idx."""
    subset = df.iloc[after_idx:]
    hits = subset[subset['High'] >= level]
    if hits.empty:
        return None
    idx = df.index.get_loc(hits.index[0])
    return hits.index[0].strftime('%Y-%m-%d'), idx


def _annualized(total_return_pct: float, days: int) -> float:
    if days <= 0:
        return 0.0
    r = total_return_pct / 100
    years = days / 365.25
    return round(((1 + r) ** (1 / years) - 1) * 100, 1)


# ─── baseline simulators ─────────────────────────────────────────────────────

@dataclass
class BaselineResult:
    ticker: str
    label: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    annualized_return_pct: float
    n_trades: int
    win_rate_pct: float
    avg_hold_days: float
    max_drawdown_pct: float
    note: str = ""


def _baseline_result(ticker, label, start, end, initial, final, n_trades=1,
                     win_pct=100.0, avg_hold=0.0, max_dd=0.0, note=""):
    days = (pd.Timestamp(end) - pd.Timestamp(start)).days
    total = round((final - initial) / initial * 100, 1)
    ann   = _annualized(total, days)
    return BaselineResult(ticker, label, start, end, initial, round(final, 2),
                          total, ann, n_trades, win_pct, avg_hold, max_dd, note)


def baseline_buy_hold(ticker: str, start_date: str, end_date: str,
                      initial_capital: float) -> BaselineResult:
    """Buy at open on start_date, hold to end_date."""
    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty:
        return _baseline_result(ticker, "Buy&Hold", start_date, end_date, initial_capital, initial_capital)
    buy_price  = float(df['Open'].iloc[0])
    sell_price = float(df['Close'].iloc[-1])
    shares     = initial_capital / buy_price
    final      = shares * sell_price

    # max drawdown: largest drop from running peak
    closes = df['Close'].values
    peak   = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak * 100
        if dd > max_dd:
            max_dd = dd

    days = (df.index[-1] - df.index[0]).days
    return _baseline_result(ticker, "Buy&Hold", start_date, end_date,
                            initial_capital, final, 1, 100.0, days, round(max_dd, 1))


def baseline_spy_dca(start_date: str, end_date: str,
                     initial_capital: float) -> BaselineResult:
    """Monthly DCA into SPY. Equal slices on first trading day of each month."""
    from backtest import generate_monthly_dates
    dates = generate_monthly_dates(start_date, end_date)
    if not dates:
        return _baseline_result("SPY", "SPY DCA", start_date, end_date,
                                initial_capital, initial_capital, note="no dates")
    df = _fetch_ohlcv("SPY", start_date, end_date)
    if df.empty:
        return _baseline_result("SPY", "SPY DCA", start_date, end_date,
                                initial_capital, initial_capital, note="no data")

    slice_amount = initial_capital / len(dates)
    total_shares = 0.0
    for d in dates:
        ts = pd.Timestamp(d)
        if df.index.tz:
            ts = ts.tz_localize('UTC')
        idx = df.index.searchsorted(ts)
        if idx >= len(df):
            idx = len(df) - 1
        price = float(df['Open'].iloc[idx])
        total_shares += slice_amount / price

    final = total_shares * float(df['Close'].iloc[-1])

    # max drawdown on portfolio value (approximate: use SPY price curve)
    closes = df['Close'].values
    peak, max_dd = closes[0], 0.0
    for c in closes:
        if c > peak: peak = c
        dd = (peak - c) / peak * 100
        if dd > max_dd: max_dd = dd

    return _baseline_result("SPY", "SPY DCA", start_date, end_date,
                            initial_capital, final, len(dates), 100.0,
                            (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days / len(dates),
                            round(max_dd, 1), f"{len(dates)} monthly buys")


def baseline_ticker_dca(ticker: str, start_date: str, end_date: str,
                        initial_capital: float) -> BaselineResult:
    """Monthly DCA into same ticker."""
    from backtest import generate_monthly_dates
    dates = generate_monthly_dates(start_date, end_date)
    if not dates:
        return _baseline_result(ticker, "DCA", start_date, end_date,
                                initial_capital, initial_capital, note="no dates")
    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty:
        return _baseline_result(ticker, "DCA", start_date, end_date,
                                initial_capital, initial_capital, note="no data")

    slice_amount = initial_capital / len(dates)
    total_shares = 0.0
    for d in dates:
        ts = pd.Timestamp(d)
        if df.index.tz:
            ts = ts.tz_localize('UTC')
        idx = df.index.searchsorted(ts)
        if idx >= len(df):
            idx = len(df) - 1
        price = float(df['Open'].iloc[idx])
        total_shares += slice_amount / price

    final = total_shares * float(df['Close'].iloc[-1])

    closes = df['Close'].values
    peak, max_dd = closes[0], 0.0
    for c in closes:
        if c > peak: peak = c
        dd = (peak - c) / peak * 100
        if dd > max_dd: max_dd = dd

    return _baseline_result(ticker, "DCA", start_date, end_date,
                            initial_capital, final, len(dates), 100.0,
                            (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days / len(dates),
                            round(max_dd, 1), f"{len(dates)} monthly buys")


def baseline_random_entry(ticker: str, start_date: str, end_date: str,
                          profit_target_pct: float, initial_capital: float,
                          n_simulations: int = 50, seed: int = 42) -> BaselineResult:
    """
    Random entry with same compound +X% exit mechanic as the sniper.
    Runs N simulations with different random seeds, returns the average.
    This directly isolates whether sniper entry TIMING adds alpha.
    """
    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty or len(df) < 5:
        return _baseline_result(ticker, f"Random+{int(profit_target_pct)}%",
                                start_date, end_date, initial_capital, initial_capital)

    rng = np.random.default_rng(seed)
    sim_finals = []

    for sim in range(n_simulations):
        capital = initial_capital
        idx = 0
        loop = 0
        while idx < len(df) - 2 and loop < 60:
            loop += 1
            # Random entry: pick a random day in remaining window
            remaining = len(df) - idx - 1
            if remaining < 2:
                break
            rand_offset = int(rng.integers(0, max(1, remaining // 2)))
            entry_idx = idx + rand_offset
            entry_price = float(df['Open'].iloc[entry_idx])
            if entry_price <= 0:
                break

            target = entry_price * (1 + profit_target_pct / 100)
            exit_idx = None
            for j in range(entry_idx + 1, len(df)):
                if df['High'].iloc[j] >= target:
                    exit_idx = j
                    break

            if exit_idx is not None:
                exit_price = target
                pnl = profit_target_pct
                idx = exit_idx
            else:
                exit_price = float(df['Close'].iloc[-1])
                pnl = (exit_price - entry_price) / entry_price * 100
                idx = len(df)

            capital *= (1 + pnl / 100)

        sim_finals.append(capital)

    avg_final = float(np.mean(sim_finals))
    total     = round((avg_final - initial_capital) / initial_capital * 100, 1)
    days      = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    ann       = _annualized(total, days)
    return BaselineResult(
        ticker=ticker,
        label=f"Random+{int(profit_target_pct)}%",
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_capital=round(avg_final, 2),
        total_return_pct=total,
        annualized_return_pct=ann,
        n_trades=0,
        win_rate_pct=0.0,
        avg_hold_days=0.0,
        max_drawdown_pct=0.0,
        note=f"avg of {n_simulations} sims",
    )


def baseline_pullback_entry(ticker: str, start_date: str, end_date: str,
                            profit_target_pct: float, initial_capital: float,
                            pullback_pct: float = 5.0) -> BaselineResult:
    """
    Dumb dip-buyer: buy whenever price drops pullback_pct% from rolling 20-day high.
    Same compound +X% exit mechanic as sniper.
    Tests whether K-Means+options beats a simple mechanical dip rule.
    """
    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty:
        return _baseline_result(ticker, f"Pullback+{int(profit_target_pct)}%",
                                start_date, end_date, initial_capital, initial_capital)

    capital = initial_capital
    trades  = 0
    wins    = 0
    hold_days_list = []
    max_capital = initial_capital
    max_dd = 0.0
    idx = 20  # need 20 days for rolling high

    while idx < len(df) - 1:
        # Rolling 20-day high
        rolling_high = float(df['High'].iloc[max(0, idx-20):idx].max())
        current_low  = float(df['Low'].iloc[idx])

        # Trigger: today's low is pullback_pct% below rolling high
        if rolling_high > 0 and current_low <= rolling_high * (1 - pullback_pct / 100):
            entry_price = float(df['Open'].iloc[idx + 1])  # next open
            if entry_price <= 0:
                idx += 1
                continue
            target = entry_price * (1 + profit_target_pct / 100)
            entry_date = df.index[idx]
            exit_idx = None

            for j in range(idx + 2, len(df)):
                if df['High'].iloc[j] >= target:
                    exit_idx = j
                    break

            if exit_idx is not None:
                exit_price = target
                pnl = profit_target_pct
                hold = (df.index[exit_idx] - entry_date).days
                wins += 1
                idx = exit_idx
            else:
                exit_price = float(df['Close'].iloc[-1])
                pnl = (exit_price - entry_price) / entry_price * 100
                hold = (df.index[-1] - entry_date).days
                idx = len(df)

            capital *= (1 + pnl / 100)
            trades  += 1
            hold_days_list.append(hold)
            max_capital = max(max_capital, capital)
            dd = (max_capital - capital) / max_capital * 100
            max_dd = max(max_dd, dd)
        else:
            idx += 1

    win_rate   = round(wins / trades * 100, 1) if trades else 0.0
    avg_hold   = round(float(np.mean(hold_days_list)), 1) if hold_days_list else 0.0
    total      = round((capital - initial_capital) / initial_capital * 100, 1)
    days       = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    ann        = _annualized(total, days)

    return BaselineResult(
        ticker=ticker,
        label=f"Pullback+{int(profit_target_pct)}%",
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_capital=round(capital, 2),
        total_return_pct=total,
        annualized_return_pct=ann,
        n_trades=trades,
        win_rate_pct=win_rate,
        avg_hold_days=avg_hold,
        max_drawdown_pct=round(max_dd, 1),
        note=f"-{pullback_pct:.0f}% from 20d high trigger",
    )


# ─── core simulator ───────────────────────────────────────────────────────────

def simulate_strategy(
    ticker: str,
    start_date: str,
    end_date: str,
    profit_target_pct: float,
    initial_capital: float = 10_000,
    verbose: bool = False,
) -> StrategyResult:
    from sniper import TechSniperAI

    strategy_label = f"+{int(profit_target_pct)}%"
    capital = initial_capital
    trades: list[Trade] = []

    # Fetch full OHLCV once for the entire period
    full_df = _fetch_ohlcv(ticker, start_date, end_date)
    if full_df.empty:
        return StrategyResult(ticker, strategy_label, start_date, end_date,
                              initial_capital, initial_capital, 0, 0, 0, 0, 0, 0, 0, [])

    current_date = start_date
    max_capital = initial_capital
    max_drawdown = 0.0
    loop_guard = 0

    while current_date < end_date and loop_guard < 60:
        loop_guard += 1

        # ── run sniper at current_date ──────────────────────────────────────
        try:
            bot = TechSniperAI(ticker, as_of_date=current_date, use_cache=True)
            if bot.current_price == 0:
                current_date = (pd.Timestamp(current_date) + timedelta(days=30)).strftime('%Y-%m-%d')
                continue
            orders = bot.generate_orders()
        except Exception as e:
            if verbose:
                console.print(f"  [red]sniper error on {current_date}: {e}[/red]")
            current_date = (pd.Timestamp(current_date) + timedelta(days=30)).strftime('%Y-%m-%d')
            continue

        if not orders:
            current_date = (pd.Timestamp(current_date) + timedelta(days=30)).strftime('%Y-%m-%d')
            continue

        # Extract levels sorted high → low (L1, L2, L3)
        levels = sorted(
            [(k, v['price']) for k, v in orders.items()],
            key=lambda x: x[1], reverse=True
        )

        # Slice OHLCV from current_date onward.
        # Normalise to same tz as the yfinance index (which is tz-aware).
        try:
            ts = pd.Timestamp(current_date)
            if full_df.index.tz is not None and ts.tz is None:
                ts = ts.tz_localize('UTC')
            from_idx = full_df.index.searchsorted(ts)
        except Exception:
            current_date = (pd.Timestamp(current_date) + timedelta(days=1)).strftime('%Y-%m-%d')
            continue

        if from_idx >= len(full_df):
            break

        fwd = full_df.iloc[from_idx:]

        # ── wait for nearest level hit ──────────────────────────────────────
        entry_result = None
        entry_level_name = None
        entry_price = None
        entry_idx = None

        for level_name, level_price in levels:
            hit = _first_hit_low(fwd, level_price)
            if hit:
                hit_date, hit_local_idx = hit
                abs_idx = from_idx + hit_local_idx
                # Use next day open as entry (realistic limit order fill)
                fill_idx = min(abs_idx + 1, len(full_df) - 1)
                fill_price = float(full_df['Open'].iloc[fill_idx])
                fill_date = full_df.index[fill_idx].strftime('%Y-%m-%d')

                if not entry_result or abs_idx < entry_idx:
                    entry_result = (fill_date, fill_price, fill_idx)
                    entry_level_name = level_name.split(' ')[0] + ' ' + level_name.split(' ')[1]
                    entry_idx = fill_idx

        if entry_result is None:
            # No entry found in remaining period — done
            break

        entry_date_str, entry_fill_price, entry_abs_idx = entry_result

        # ── wait for profit target from entry ───────────────────────────────
        target_price = entry_fill_price * (1 + profit_target_pct / 100)
        post_entry = full_df.iloc[entry_abs_idx + 1:]

        exit_date_str = None
        exit_price = None
        target_hit = False
        open_pos = False

        if not post_entry.empty:
            tp_hit = _first_hit_high(post_entry, target_price)
            if tp_hit:
                exit_date_str, _ = tp_hit
                exit_price = target_price
                target_hit = True
            else:
                # Period ended without hitting target
                exit_date_str = full_df.index[-1].strftime('%Y-%m-%d')
                exit_price = float(full_df['Close'].iloc[-1])
                open_pos = True
        else:
            exit_date_str = entry_date_str
            exit_price = entry_fill_price
            open_pos = True

        pnl_pct = (exit_price - entry_fill_price) / entry_fill_price * 100
        hold_days = (pd.Timestamp(exit_date_str) - pd.Timestamp(entry_date_str)).days

        # Update capital
        capital = capital * (1 + pnl_pct / 100)
        max_capital = max(max_capital, capital)
        drawdown = (max_capital - capital) / max_capital * 100
        max_drawdown = max(max_drawdown, drawdown)

        trades.append(Trade(
            ticker=ticker,
            strategy=strategy_label,
            start_date=start_date,
            analysis_date=current_date,
            entry_date=entry_date_str,
            entry_price=round(entry_fill_price, 2),
            entry_level=entry_level_name,
            exit_date=exit_date_str,
            exit_price=round(exit_price, 2),
            pnl_pct=round(pnl_pct, 2),
            hold_days=hold_days,
            target_hit=target_hit,
            open_position=open_pos,
        ))

        if verbose:
            status = "HIT" if target_hit else ("open" if open_pos else "closed")
            console.print(
                f"  {current_date} | entry {entry_date_str} ${entry_fill_price:.2f} "
                f"-> exit {exit_date_str} ${exit_price:.2f} "
                f"({pnl_pct:+.1f}%) [{status}]"
            )

        if open_pos:
            break

        # Re-run from exit date
        current_date = exit_date_str

    # ── compute summary stats ─────────────────────────────────────────────
    n = len(trades)
    n_hits = sum(1 for t in trades if t.target_hit)
    total_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    total_return = round((capital - initial_capital) / initial_capital * 100, 1)
    ann = _annualized(total_return, total_days)
    win_rate = round(n_hits / n * 100, 1) if n > 0 else 0.0
    avg_hold = round(np.mean([t.hold_days for t in trades]), 1) if trades else 0.0

    return StrategyResult(
        ticker=ticker,
        strategy=strategy_label,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_capital=round(capital, 2),
        total_return_pct=total_return,
        annualized_return_pct=ann,
        n_trades=n,
        n_target_hits=n_hits,
        win_rate_pct=win_rate,
        avg_hold_days=avg_hold,
        max_drawdown_pct=round(max_drawdown, 1),
        trades=trades,
    )


# ─── benchmark runner ─────────────────────────────────────────────────────────

def run_benchmark(
    tickers: list[str],
    start_dates: list[str],
    end_date: str,
    targets: list[float],
    initial_capital: float,
    verbose: bool,
    export_dir: str,
) -> tuple[list[StrategyResult], list[BaselineResult]]:

    all_sniper:   list[StrategyResult]  = []
    all_baselines: list[BaselineResult] = []

    for ticker in tickers:
        console.print()
        console.print(Rule(f"[bold cyan]{ticker}[/bold cyan]"))

        for start in start_dates:
            console.print(f"\n  [dim]Start: {start} -> {end_date}[/dim]")

            # ── sniper strategies ──────────────────────────────────────────
            sniper_results = []
            for target in targets:
                label = f"+{int(target)}%"
                with console.status(f"  [cyan]Sniper {label} {ticker} from {start}...[/cyan]"):
                    r = simulate_strategy(ticker, start, end_date, target,
                                         initial_capital=initial_capital, verbose=verbose)
                sniper_results.append(r)
                all_sniper.append(r)

            # ── baselines ──────────────────────────────────────────────────
            baselines = []
            with console.status(f"  [dim]Computing baselines for {ticker} {start}...[/dim]"):
                baselines.append(baseline_buy_hold(ticker, start, end_date, initial_capital))
                baselines.append(baseline_ticker_dca(ticker, start, end_date, initial_capital))
                baselines.append(baseline_spy_dca(start, end_date, initial_capital))
                for target in targets:
                    baselines.append(baseline_random_entry(ticker, start, end_date, target, initial_capital))
                    baselines.append(baseline_pullback_entry(ticker, start, end_date, target, initial_capital))
            all_baselines.extend(baselines)

            # ── head-to-head comparison table ──────────────────────────────
            _print_comparison_table(ticker, start, end_date, sniper_results, baselines, targets)

    return all_sniper, all_baselines


def _print_comparison_table(ticker, start, end, sniper_results, baselines, targets):
    """Head-to-head: Sniper vs all baselines for a given ticker/start."""
    tbl = Table(
        title=f"Head-to-Head: {ticker}  {start} -> {end}",
        box=box.ROUNDED, header_style="bold", show_header=True
    )
    tbl.add_column("Strategy",      min_width=22)
    tbl.add_column("Total Return",  justify="right", min_width=13)
    tbl.add_column("Ann. Return",   justify="right", min_width=12)
    tbl.add_column("Final $",       justify="right", min_width=11)
    tbl.add_column("Trades",        justify="right", min_width=8)
    tbl.add_column("Win Rate",      justify="right", min_width=10)
    tbl.add_column("Avg Hold",      justify="right", min_width=10)
    tbl.add_column("Max DD",        justify="right", min_width=9)
    tbl.add_column("Note",          min_width=18)

    def _row(label, total, ann, final, trades, wr, hold, dd, note, style=""):
        rc = "green" if total >= 0 else "red"
        tbl.add_row(
            f"[{style}]{label}[/{style}]" if style else label,
            f"[{rc}]{total:+.1f}%[/{rc}]",
            f"[{rc}]{ann:+.1f}%[/{rc}]",
            f"${final:,.0f}",
            str(trades) if trades else "-",
            f"{wr:.0f}%" if wr else "-",
            f"{hold:.0f}d" if hold else "-",
            f"{dd:.1f}%",
            note,
        )

    # Sniper rows
    tbl.add_section()
    for r in sniper_results:
        _row(f"Sniper {r.strategy}", r.total_return_pct, r.annualized_return_pct,
             r.final_capital, r.n_trades, r.win_rate_pct, r.avg_hold_days,
             r.max_drawdown_pct, "support levels + exit", "bold cyan")

    # Baseline: Buy&Hold + DCA (no target-specific)
    tbl.add_section()
    bh  = next((b for b in baselines if b.label == "Buy&Hold"), None)
    dca = next((b for b in baselines if b.label == "DCA"), None)
    spy = next((b for b in baselines if b.label == "SPY DCA"), None)
    if bh:
        _row("Buy & Hold", bh.total_return_pct, bh.annualized_return_pct,
             bh.final_capital, bh.n_trades, bh.win_rate_pct, bh.avg_hold_days,
             bh.max_drawdown_pct, "buy open, hold to end", "dim")
    if dca:
        _row(f"DCA {ticker}", dca.total_return_pct, dca.annualized_return_pct,
             dca.final_capital, dca.n_trades, dca.win_rate_pct, dca.avg_hold_days,
             dca.max_drawdown_pct, dca.note, "dim")
    if spy:
        _row("SPY DCA", spy.total_return_pct, spy.annualized_return_pct,
             spy.final_capital, spy.n_trades, spy.win_rate_pct, spy.avg_hold_days,
             spy.max_drawdown_pct, spy.note, "dim")

    # Baseline: Random + Pullback per target
    for target in targets:
        tbl.add_section()
        rand = next((b for b in baselines if b.label == f"Random+{int(target)}%"), None)
        pull = next((b for b in baselines if b.label == f"Pullback+{int(target)}%"), None)
        if rand:
            _row(f"Random entry +{int(target)}%", rand.total_return_pct,
                 rand.annualized_return_pct, rand.final_capital,
                 rand.n_trades, rand.win_rate_pct, rand.avg_hold_days,
                 rand.max_drawdown_pct, rand.note, "yellow")
        if pull:
            _row(f"Pullback -5% +{int(target)}%", pull.total_return_pct,
                 pull.annualized_return_pct, pull.final_capital,
                 pull.n_trades, pull.win_rate_pct, pull.avg_hold_days,
                 pull.max_drawdown_pct, pull.note, "yellow")

    console.print(tbl)


def _print_start_table(ticker, start, end, results):
    tbl = Table(
        title=f"{ticker}  {start} -> {end}",
        box=box.ROUNDED, header_style="bold", show_header=True
    )
    tbl.add_column("Strategy",    min_width=10)
    tbl.add_column("Total Return", justify="right", min_width=13)
    tbl.add_column("Ann. Return",  justify="right", min_width=12)
    tbl.add_column("Final $",      justify="right", min_width=11)
    tbl.add_column("Trades",       justify="right", min_width=8)
    tbl.add_column("Win Rate",     justify="right", min_width=10)
    tbl.add_column("Avg Hold",     justify="right", min_width=10)
    tbl.add_column("Max DD",       justify="right", min_width=9)

    for r in results:
        rc = "green" if r.total_return_pct >= 0 else "red"
        tbl.add_row(
            f"[bold]{r.strategy}[/bold]",
            f"[{rc}]{r.total_return_pct:+.1f}%[/{rc}]",
            f"[{rc}]{r.annualized_return_pct:+.1f}%[/{rc}]",
            f"${r.final_capital:,.0f}",
            str(r.n_trades),
            f"{r.win_rate_pct:.0f}%",
            f"{r.avg_hold_days:.0f}d",
            f"{r.max_drawdown_pct:.1f}%",
        )
    console.print(tbl)


def _print_grand_summary(all_sniper: list[StrategyResult],
                         all_baselines: list[BaselineResult],
                         targets: list[float]):
    """Cross-ticker summary: avg return per strategy."""
    console.print()
    console.print(Rule("[bold white]GRAND SUMMARY — Average across all tickers & start points[/bold white]"))

    tbl = Table(box=box.ROUNDED, header_style="bold")
    tbl.add_column("Strategy",      min_width=10)
    tbl.add_column("Avg Return",    justify="right", min_width=12)
    tbl.add_column("Avg Ann.",      justify="right", min_width=11)
    tbl.add_column("Avg Trades",    justify="right", min_width=11)
    tbl.add_column("Avg Win Rate",  justify="right", min_width=12)
    tbl.add_column("Avg Hold",      justify="right", min_width=10)
    tbl.add_column("Avg Max DD",    justify="right", min_width=11)
    tbl.add_column("Best",          min_width=20)
    tbl.add_column("Worst",         min_width=20)

    for t in targets:
        label = f"+{int(t)}%"
        bucket = [r for r in all_sniper if r.strategy == label]
        if not bucket:
            continue

        avg_ret  = np.mean([r.total_return_pct for r in bucket])
        avg_ann  = np.mean([r.annualized_return_pct for r in bucket])
        avg_tr   = np.mean([r.n_trades for r in bucket])
        avg_wr   = np.mean([r.win_rate_pct for r in bucket])
        avg_hold = np.mean([r.avg_hold_days for r in bucket])
        avg_dd   = np.mean([r.max_drawdown_pct for r in bucket])
        best     = max(bucket, key=lambda r: r.total_return_pct)
        worst    = min(bucket, key=lambda r: r.total_return_pct)

        rc = "green" if avg_ret >= 0 else "red"
        tbl.add_row(
            f"[bold cyan]Sniper {label}[/bold cyan]",
            f"[{rc}]{avg_ret:+.1f}%[/{rc}]",
            f"[{rc}]{avg_ann:+.1f}%[/{rc}]",
            f"{avg_tr:.1f}",
            f"{avg_wr:.0f}%",
            f"{avg_hold:.0f}d",
            f"{avg_dd:.1f}%",
            f"[green]{best.ticker} {best.start_date}: {best.total_return_pct:+.0f}%[/green]",
            f"[red]{worst.ticker} {worst.start_date}: {worst.total_return_pct:+.0f}%[/red]",
        )

    # Baseline rows
    tbl.add_section()
    for blabel in ["Buy&Hold", "DCA", "SPY DCA"]:
        bucket = [b for b in all_baselines if b.label == blabel]
        if not bucket:
            continue
        avg_ret = np.mean([b.total_return_pct for b in bucket])
        avg_ann = np.mean([b.annualized_return_pct for b in bucket])
        avg_dd  = np.mean([b.max_drawdown_pct for b in bucket])
        rc = "green" if avg_ret >= 0 else "red"
        tbl.add_row(
            f"[dim]{blabel}[/dim]",
            f"[{rc}]{avg_ret:+.1f}%[/{rc}]",
            f"[{rc}]{avg_ann:+.1f}%[/{rc}]",
            "-", "-", "-",
            f"{avg_dd:.1f}%", "-", "-",
        )

    tbl.add_section()
    for t in targets:
        for blabel in [f"Random+{int(t)}%", f"Pullback+{int(t)}%"]:
            bucket = [b for b in all_baselines if b.label == blabel]
            if not bucket:
                continue
            avg_ret = np.mean([b.total_return_pct for b in bucket])
            avg_ann = np.mean([b.annualized_return_pct for b in bucket])
            avg_tr  = np.mean([b.n_trades for b in bucket])
            avg_wr  = np.mean([b.win_rate_pct for b in bucket])
            avg_dd  = np.mean([b.max_drawdown_pct for b in bucket])
            rc = "green" if avg_ret >= 0 else "red"
            tbl.add_row(
                f"[yellow]{blabel}[/yellow]",
                f"[{rc}]{avg_ret:+.1f}%[/{rc}]",
                f"[{rc}]{avg_ann:+.1f}%[/{rc}]",
                f"{avg_tr:.1f}" if avg_tr else "-",
                f"{avg_wr:.0f}%" if avg_wr else "-",
                "-", f"{avg_dd:.1f}%", "-", "-",
            )

    console.print(tbl)


def export_results(all_results: list[StrategyResult],
                   all_baselines: list[BaselineResult], out_dir: str):
    os.makedirs(out_dir, exist_ok=True)

    # Summary CSV
    summary_path = os.path.join(out_dir, "benchmark_summary.csv")
    with open(summary_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['ticker','strategy','start_date','end_date',
                    'total_return_pct','annualized_return_pct','final_capital',
                    'n_trades','win_rate_pct','avg_hold_days','max_drawdown_pct'])
        for r in all_results:
            w.writerow([r.ticker, r.strategy, r.start_date, r.end_date,
                        r.total_return_pct, r.annualized_return_pct, r.final_capital,
                        r.n_trades, r.win_rate_pct, r.avg_hold_days, r.max_drawdown_pct])

    # Trades CSV
    trades_path = os.path.join(out_dir, "benchmark_trades.csv")
    with open(trades_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['ticker','strategy','start_date','analysis_date',
                    'entry_date','entry_price','entry_level',
                    'exit_date','exit_price','pnl_pct','hold_days',
                    'target_hit','open_position'])
        for r in all_results:
            for t in r.trades:
                w.writerow([t.ticker, t.strategy, t.start_date, t.analysis_date,
                            t.entry_date, t.entry_price, t.entry_level,
                            t.exit_date, t.exit_price, t.pnl_pct, t.hold_days,
                            t.target_hit, t.open_position])

    # Baselines CSV
    baselines_path = os.path.join(out_dir, "benchmark_baselines.csv")
    with open(baselines_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['ticker','label','start_date','end_date',
                    'total_return_pct','annualized_return_pct','final_capital',
                    'n_trades','win_rate_pct','avg_hold_days','max_drawdown_pct','note'])
        for b in all_baselines:
            w.writerow([b.ticker, b.label, b.start_date, b.end_date,
                        b.total_return_pct, b.annualized_return_pct, b.final_capital,
                        b.n_trades, b.win_rate_pct, b.avg_hold_days,
                        b.max_drawdown_pct, b.note])

    console.print(f"\n[green]Summary   -> {summary_path}[/green]")
    console.print(f"[green]Trades    -> {trades_path}[/green]")
    console.print(f"[green]Baselines -> {baselines_path}[/green]")


# ─── main ─────────────────────────────────────────────────────────────────────

DEFAULT_TICKERS = ["MSFT", "AAPL", "NVDA", "GOOGL", "META", "TSLA", "AMD"]
DEFAULT_STARTS  = ["2023-01-01", "2023-07-01", "2024-01-01", "2024-07-01"]
DEFAULT_END     = "2026-06-01"
DEFAULT_TARGETS = [5.0, 10.0, 15.0, 20.0]
DEFAULT_CAPITAL = 10_000

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Value Sniper Strategy Benchmark')
    parser.add_argument('--tickers',  nargs='+', default=DEFAULT_TICKERS)
    parser.add_argument('--starts',   nargs='+', default=DEFAULT_STARTS,
                        help='Multiple start dates to test')
    parser.add_argument('--end',      default=DEFAULT_END)
    parser.add_argument('--targets',  nargs='+', type=float, default=DEFAULT_TARGETS,
                        help='Profit targets in %% (e.g. 5 10 15 20)')
    parser.add_argument('--capital',  type=float, default=DEFAULT_CAPITAL)
    parser.add_argument('--verbose',  action='store_true')
    parser.add_argument('--out',      default=None, help='Output directory (default: _runtime/)')
    args = parser.parse_args()

    out_dir = args.out or os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', '_runtime')
    )

    console.print(Panel(
        f"Tickers : [cyan]{' '.join(args.tickers)}[/cyan]\n"
        f"Starts  : [cyan]{' '.join(args.starts)}[/cyan]\n"
        f"End     : [cyan]{args.end}[/cyan]\n"
        f"Targets : [cyan]{', '.join(f'+{int(t)}%' for t in args.targets)}[/cyan]\n"
        f"Capital : [cyan]${args.capital:,.0f}[/cyan]",
        title="[bold]VALUE SNIPER BENCHMARK[/bold]"
    ))

    all_sniper, all_baselines = run_benchmark(
        tickers=args.tickers,
        start_dates=args.starts,
        end_date=args.end,
        targets=args.targets,
        initial_capital=args.capital,
        verbose=args.verbose,
        export_dir=out_dir,
    )

    _print_grand_summary(all_sniper, all_baselines, args.targets)
    export_results(all_sniper, all_baselines, out_dir)
