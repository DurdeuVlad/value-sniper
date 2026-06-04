"""
Value Sniper — Strategy Benchmark

Compares Value Sniper against 14 entry strategies across two groups:

  Hold Forever — one entry per period, hold to end date (tests pure entry quality)
    Buy & Hold, Ticker DCA, SPY DCA, Sniper Hold, Breakout 20d, RSI>50,
    SMA200 Bounce, Golden Cross, Vol Surge

  Sell at +X%, Re-enter — compound cycling at each profit target
    Immediate Rebuy, Random Entry, Pullback -5%, DCA+Exit, Breakout 20d,
    RSI>50, SMA200 Bounce, Golden Cross, Vol Surge

Default targets: +5%, +10%, +25%, +50%

Usage:
  python src/benchmark.py
  python src/benchmark.py --tickers MSFT AAPL NVDA --starts 2023-01-01 --end 2026-01-01
  python src/benchmark.py --targets 10 25 50 --capital 10000
"""

import argparse
import os
import sys
import io
import csv
from dataclasses import dataclass, field
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


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan).fillna(1e-10)
    return 100 - (100 / (1 + rs))


def _yearly_from_caps(year_caps: dict, initial_capital: float) -> dict:
    """Convert {year: end_capital} snapshots to {year: pct_return_that_year}."""
    if not year_caps:
        return {}
    yearly = {}
    prev = initial_capital
    for yr in sorted(year_caps):
        cap = year_caps[yr]
        yearly[yr] = round((cap - prev) / prev * 100, 1)
        prev = cap
    return yearly


def _ohlcv_yearly(df: pd.DataFrame, entry_date, shares: float,
                  initial_capital: float) -> dict:
    """For a buy-and-hold position, compute year-end capital from OHLCV closes."""
    ts = entry_date if hasattr(entry_date, 'year') else pd.Timestamp(entry_date)
    if df.index.tz and getattr(ts, 'tz', None) is None:
        ts = ts.tz_localize('UTC')
    year_caps = {}
    for dt, row in df[df.index >= ts].iterrows():
        year_caps[dt.year] = shares * float(row['Close'])
    return _yearly_from_caps(year_caps, initial_capital)


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
    yearly_returns: dict = field(default_factory=dict)


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
    r = _baseline_result(ticker, "Buy&Hold", start_date, end_date,
                         initial_capital, final, 1, 100.0, days, round(max_dd, 1))
    r.yearly_returns = _ohlcv_yearly(df, df.index[0], shares, initial_capital)
    return r


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

    r = _baseline_result("SPY", "SPY DCA", start_date, end_date,
                         initial_capital, final, len(dates), 100.0,
                         (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days / len(dates),
                         round(max_dd, 1), f"{len(dates)} monthly buys")
    # Approximate yearly: recompute portfolio value year by year
    df_spy = _fetch_ohlcv("SPY", start_date, end_date)
    if not df_spy.empty:
        year_caps: dict = {}
        running_shares = 0.0
        slice_amt = initial_capital / len(dates)
        di = 0
        for d in dates:
            ts2 = pd.Timestamp(d)
            if df_spy.index.tz and ts2.tz is None:
                ts2 = ts2.tz_localize('UTC')
            ix = df_spy.index.searchsorted(ts2)
            if ix >= len(df_spy): ix = len(df_spy) - 1
            running_shares += slice_amt / float(df_spy['Open'].iloc[ix])
        # Re-walk for per-year snapshot using cumulative shares after each purchase
        running_shares2 = 0.0
        date_idx = 0
        for i, (dt, row) in enumerate(df_spy.iterrows()):
            while date_idx < len(dates):
                ts2 = pd.Timestamp(dates[date_idx])
                if df_spy.index.tz and ts2.tz is None:
                    ts2 = ts2.tz_localize('UTC')
                if dt >= ts2:
                    running_shares2 += slice_amt / float(df_spy['Open'].iloc[i])
                    date_idx += 1
                else:
                    break
            if running_shares2 > 0:
                year_caps[dt.year] = running_shares2 * float(row['Close'])
        r.yearly_returns = _yearly_from_caps(year_caps, initial_capital)
    return r


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

    r = _baseline_result(ticker, "DCA", start_date, end_date,
                         initial_capital, final, len(dates), 100.0,
                         (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days / len(dates),
                         round(max_dd, 1), f"{len(dates)} monthly buys")
    year_caps2: dict = {}
    running_sh = 0.0
    slice_amt2 = initial_capital / len(dates)
    date_idx2 = 0
    for i2, (dt2, row2) in enumerate(df.iterrows()):
        while date_idx2 < len(dates):
            ts3 = pd.Timestamp(dates[date_idx2])
            if df.index.tz and ts3.tz is None:
                ts3 = ts3.tz_localize('UTC')
            if dt2 >= ts3:
                running_sh += slice_amt2 / float(df['Open'].iloc[i2])
                date_idx2 += 1
            else:
                break
        if running_sh > 0:
            year_caps2[dt2.year] = running_sh * float(row2['Close'])
    r.yearly_returns = _yearly_from_caps(year_caps2, initial_capital)
    return r


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
    year_caps: dict = {}
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
            year_caps[df.index[min(idx, len(df)-1)].year] = capital
        else:
            idx += 1

    win_rate   = round(wins / trades * 100, 1) if trades else 0.0
    avg_hold   = round(float(np.mean(hold_days_list)), 1) if hold_days_list else 0.0
    total      = round((capital - initial_capital) / initial_capital * 100, 1)
    days       = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    ann        = _annualized(total, days)

    r = BaselineResult(
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
    r.yearly_returns = _yearly_from_caps(year_caps, initial_capital)
    return r


def baseline_immediate_rebuy(ticker: str, start_date: str, end_date: str,
                              profit_target_pct: float,
                              initial_capital: float) -> BaselineResult:
    """Dumbest re-entry: sell at target, buy next open, repeat. Lower bound baseline."""
    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty:
        return _baseline_result(ticker, f"ImmediateRebuy+{int(profit_target_pct)}%",
                                start_date, end_date, initial_capital, initial_capital)

    capital = initial_capital
    trades = wins = 0
    hold_days_list = []
    max_capital = initial_capital
    max_dd = 0.0
    year_caps: dict = {}
    idx = 0

    while idx < len(df) - 1:
        entry_price = float(df['Open'].iloc[idx])
        if entry_price <= 0:
            idx += 1
            continue
        target = entry_price * (1 + profit_target_pct / 100)
        entry_date = df.index[idx]
        exit_idx = None
        for j in range(idx + 1, len(df)):
            if df['High'].iloc[j] >= target:
                exit_idx = j
                break
        if exit_idx is not None:
            pnl = profit_target_pct
            hold = (df.index[exit_idx] - entry_date).days
            wins += 1
            idx = exit_idx
        else:
            pnl = (float(df['Close'].iloc[-1]) - entry_price) / entry_price * 100
            hold = (df.index[-1] - entry_date).days
            idx = len(df)
        capital *= (1 + pnl / 100)
        trades += 1
        hold_days_list.append(hold)
        max_capital = max(max_capital, capital)
        max_dd = max(max_dd, (max_capital - capital) / max_capital * 100)
        exit_dt = df.index[min(idx, len(df)-1)]
        year_caps[exit_dt.year] = capital

    win_rate = round(wins / trades * 100, 1) if trades else 0.0
    avg_hold = round(float(np.mean(hold_days_list)), 1) if hold_days_list else 0.0
    days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    total = round((capital - initial_capital) / initial_capital * 100, 1)
    r = BaselineResult(
        ticker=ticker, label=f"ImmediateRebuy+{int(profit_target_pct)}%",
        start_date=start_date, end_date=end_date,
        initial_capital=initial_capital, final_capital=round(capital, 2),
        total_return_pct=total, annualized_return_pct=_annualized(total, days),
        n_trades=trades, win_rate_pct=win_rate, avg_hold_days=avg_hold,
        max_drawdown_pct=round(max_dd, 1), note="buy open, sell at target, repeat",
    )
    r.yearly_returns = _yearly_from_caps(year_caps, initial_capital)
    return r


def baseline_dca_with_exit(ticker: str, start_date: str, end_date: str,
                            profit_target_pct: float,
                            initial_capital: float) -> BaselineResult:
    """Monthly DCA accumulation with compound exit: when position hits +X%, sell all and restart."""
    from backtest import generate_monthly_dates
    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty:
        return _baseline_result(ticker, f"DCA+{int(profit_target_pct)}%",
                                start_date, end_date, initial_capital, initial_capital)

    monthly_dates = generate_monthly_dates(start_date, end_date)
    if not monthly_dates:
        return _baseline_result(ticker, f"DCA+{int(profit_target_pct)}%",
                                start_date, end_date, initial_capital, initial_capital,
                                note="no monthly dates")

    slice_amount = initial_capital / len(monthly_dates)
    capital = initial_capital
    trades = wins = 0
    hold_days_list = []
    max_capital = initial_capital
    max_dd = 0.0

    # State for current accumulation cycle
    shares = 0.0
    total_cost = 0.0
    cycle_start_date = None
    monthly_idx = 0  # pointer into monthly_dates

    for idx in range(len(df)):
        row_date = df.index[idx]
        row_date_str = row_date.strftime('%Y-%m-%d') if hasattr(row_date, 'strftime') else str(row_date)[:10]

        # Buy monthly slice if this day matches (or is past) the next monthly date
        while monthly_idx < len(monthly_dates):
            md = monthly_dates[monthly_idx]
            ts = pd.Timestamp(md)
            if df.index.tz and ts.tz is None:
                ts = ts.tz_localize('UTC')
            if row_date >= ts:
                buy_price = float(df['Open'].iloc[idx])
                if buy_price > 0 and capital >= slice_amount:
                    bought = slice_amount / buy_price
                    shares += bought
                    total_cost += slice_amount
                    capital -= slice_amount
                    if cycle_start_date is None:
                        cycle_start_date = row_date
                monthly_idx += 1
            else:
                break

        # Check if current position hits profit target
        if shares > 0 and total_cost > 0:
            avg_cost = total_cost / shares
            target_price = avg_cost * (1 + profit_target_pct / 100)
            if float(df['High'].iloc[idx]) >= target_price:
                proceeds = shares * target_price
                pnl = (proceeds - total_cost) / total_cost * 100
                hold = (row_date - cycle_start_date).days if cycle_start_date else 0
                capital += proceeds
                trades += 1
                if pnl > 0:
                    wins += 1
                hold_days_list.append(hold)
                # Reset cycle
                shares = 0.0
                total_cost = 0.0
                cycle_start_date = None
                max_capital = max(max_capital, capital)
                max_dd = max(max_dd, (max_capital - capital) / max_capital * 100)

    # Close any open position at end
    if shares > 0:
        final_price = float(df['Close'].iloc[-1])
        capital += shares * final_price
        trades += 1
        hold_days_list.append(
            (df.index[-1] - cycle_start_date).days if cycle_start_date else 0)

    win_rate = round(wins / trades * 100, 1) if trades else 0.0
    avg_hold = round(float(np.mean(hold_days_list)), 1) if hold_days_list else 0.0
    days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    total = round((capital - initial_capital) / initial_capital * 100, 1)
    return BaselineResult(
        ticker=ticker, label=f"DCA+{int(profit_target_pct)}%",
        start_date=start_date, end_date=end_date,
        initial_capital=initial_capital, final_capital=round(capital, 2),
        total_return_pct=total, annualized_return_pct=_annualized(total, days),
        n_trades=trades, win_rate_pct=win_rate, avg_hold_days=avg_hold,
        max_drawdown_pct=round(max_dd, 1),
        note=f"monthly DCA, exit at +{int(profit_target_pct)}% avg cost",
    )


def baseline_breakout_entry(ticker: str, start_date: str, end_date: str,
                             profit_target_pct: float, initial_capital: float,
                             breakout_window: int = 20,
                             hold_to_end: bool = False) -> BaselineResult:
    """FOMO buyer: buy when price breaks above N-day rolling high."""
    label_suffix = "Hold" if hold_to_end else f"+{int(profit_target_pct)}%"
    label = f"Breakout{breakout_window}d {label_suffix}"

    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty or len(df) <= breakout_window + 1:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note=f"no breakout signal in period")

    rolling_high = df['High'].rolling(breakout_window).max().shift(1)
    capital = initial_capital
    trades = wins = 0
    hold_days_list = []
    max_capital = initial_capital
    max_dd = 0.0
    year_caps: dict = {}
    ht_entry_date = None
    ht_shares = 0.0
    idx = breakout_window  # skip NaN window

    while idx < len(df) - 1:
        rh = rolling_high.iloc[idx]
        if pd.isna(rh):
            idx += 1
            continue
        if float(df['High'].iloc[idx]) >= float(rh):
            entry_price = float(df['Open'].iloc[idx + 1])
            if entry_price <= 0:
                idx += 1
                continue
            entry_date = df.index[idx + 1]
            if hold_to_end:
                ht_shares = initial_capital / entry_price
                ht_entry_date = entry_date
                exit_price = float(df['Close'].iloc[-1])
                pnl = (exit_price - entry_price) / entry_price * 100
                hold = (df.index[-1] - entry_date).days
                capital *= (1 + pnl / 100)
                trades += 1
                if pnl > 0: wins += 1
                hold_days_list.append(hold)
                break
            else:
                target = entry_price * (1 + profit_target_pct / 100)
                exit_idx = None
                for j in range(idx + 2, len(df)):
                    if df['High'].iloc[j] >= target:
                        exit_idx = j
                        break
                if exit_idx is not None:
                    pnl = profit_target_pct
                    hold = (df.index[exit_idx] - entry_date).days
                    wins += 1
                    idx = exit_idx
                else:
                    pnl = (float(df['Close'].iloc[-1]) - entry_price) / entry_price * 100
                    hold = (df.index[-1] - entry_date).days
                    idx = len(df)
                capital *= (1 + pnl / 100)
                trades += 1
                hold_days_list.append(hold)
                max_capital = max(max_capital, capital)
                max_dd = max(max_dd, (max_capital - capital) / max_capital * 100)
                year_caps[df.index[min(idx, len(df)-1)].year] = capital
        else:
            idx += 1

    if not trades:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note=f"no {breakout_window}d breakout in period")

    win_rate = round(wins / trades * 100, 1) if trades else 0.0
    avg_hold = round(float(np.mean(hold_days_list)), 1) if hold_days_list else 0.0
    days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    total = round((capital - initial_capital) / initial_capital * 100, 1)
    r = BaselineResult(
        ticker=ticker, label=label,
        start_date=start_date, end_date=end_date,
        initial_capital=initial_capital, final_capital=round(capital, 2),
        total_return_pct=total, annualized_return_pct=_annualized(total, days),
        n_trades=trades, win_rate_pct=win_rate, avg_hold_days=avg_hold,
        max_drawdown_pct=round(max_dd, 1),
        note=f"new {breakout_window}d high trigger",
    )
    r.yearly_returns = (_ohlcv_yearly(df, ht_entry_date, ht_shares, initial_capital)
                        if hold_to_end else _yearly_from_caps(year_caps, initial_capital))
    return r


def baseline_ath_breakout_entry(ticker: str, start_date: str, end_date: str,
                                 profit_target_pct: float, initial_capital: float,
                                 hold_to_end: bool = False) -> BaselineResult:
    """Buy on new 52-week high. Strongest FOMO signal."""
    r = baseline_breakout_entry(ticker, start_date, end_date, profit_target_pct,
                                initial_capital, breakout_window=252,
                                hold_to_end=hold_to_end)
    r.label = "52wkBreakout Hold" if hold_to_end else f"52wkBreakout+{int(profit_target_pct)}%"
    r.note = "new 52-week high trigger"
    return r


def baseline_rsi_entry(ticker: str, start_date: str, end_date: str,
                        profit_target_pct: float, initial_capital: float,
                        rsi_period: int = 14, rsi_threshold: float = 50.0,
                        hold_to_end: bool = False) -> BaselineResult:
    """Trend-follower: buy when RSI crosses above threshold (uptrend confirmation)."""
    label_suffix = "Hold" if hold_to_end else f"+{int(profit_target_pct)}%"
    label = f"RSI>{int(rsi_threshold)} {label_suffix}"

    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty or len(df) <= rsi_period + 2:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note=f"no RSI>{int(rsi_threshold)} cross in period")

    rsi = _compute_rsi(df['Close'], rsi_period)
    capital = initial_capital
    trades = wins = 0
    hold_days_list = []
    max_capital = initial_capital
    max_dd = 0.0
    year_caps: dict = {}
    ht_entry_date = None
    ht_shares = 0.0
    idx = rsi_period + 1

    while idx < len(df) - 1:
        prev_rsi = rsi.iloc[idx - 1]
        curr_rsi = rsi.iloc[idx]
        if pd.isna(prev_rsi) or pd.isna(curr_rsi):
            idx += 1
            continue
        if float(prev_rsi) < rsi_threshold and float(curr_rsi) >= rsi_threshold:
            entry_price = float(df['Open'].iloc[idx + 1])
            if entry_price <= 0:
                idx += 1
                continue
            entry_date = df.index[idx + 1]
            if hold_to_end:
                ht_shares = initial_capital / entry_price
                ht_entry_date = entry_date
                exit_price = float(df['Close'].iloc[-1])
                pnl = (exit_price - entry_price) / entry_price * 100
                hold = (df.index[-1] - entry_date).days
                capital *= (1 + pnl / 100)
                trades += 1
                if pnl > 0: wins += 1
                hold_days_list.append(hold)
                break
            else:
                target = entry_price * (1 + profit_target_pct / 100)
                exit_idx = None
                for j in range(idx + 2, len(df)):
                    if df['High'].iloc[j] >= target:
                        exit_idx = j
                        break
                if exit_idx is not None:
                    pnl = profit_target_pct
                    hold = (df.index[exit_idx] - entry_date).days
                    wins += 1
                    idx = exit_idx
                else:
                    pnl = (float(df['Close'].iloc[-1]) - entry_price) / entry_price * 100
                    hold = (df.index[-1] - entry_date).days
                    idx = len(df)
                capital *= (1 + pnl / 100)
                trades += 1
                hold_days_list.append(hold)
                max_capital = max(max_capital, capital)
                max_dd = max(max_dd, (max_capital - capital) / max_capital * 100)
                year_caps[df.index[min(idx, len(df)-1)].year] = capital
        else:
            idx += 1

    if not trades:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note=f"no RSI>{int(rsi_threshold)} cross in period")

    win_rate = round(wins / trades * 100, 1) if trades else 0.0
    avg_hold = round(float(np.mean(hold_days_list)), 1) if hold_days_list else 0.0
    days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    total = round((capital - initial_capital) / initial_capital * 100, 1)
    r = BaselineResult(
        ticker=ticker, label=label,
        start_date=start_date, end_date=end_date,
        initial_capital=initial_capital, final_capital=round(capital, 2),
        total_return_pct=total, annualized_return_pct=_annualized(total, days),
        n_trades=trades, win_rate_pct=win_rate, avg_hold_days=avg_hold,
        max_drawdown_pct=round(max_dd, 1),
        note=f"RSI({rsi_period}) cross above {rsi_threshold:.0f}",
    )
    r.yearly_returns = (_ohlcv_yearly(df, ht_entry_date, ht_shares, initial_capital)
                        if hold_to_end else _yearly_from_caps(year_caps, initial_capital))
    return r


def baseline_sma200_bounce(ticker: str, start_date: str, end_date: str,
                            profit_target_pct: float, initial_capital: float,
                            hold_to_end: bool = False) -> BaselineResult:
    """Classic support: buy when price touches SMA-200 intraday then closes above it."""
    label_suffix = "Hold" if hold_to_end else f"+{int(profit_target_pct)}%"
    label = f"SMA200Bounce {label_suffix}"

    extended_start = (pd.Timestamp(start_date) - timedelta(days=310)).strftime('%Y-%m-%d')
    df_ext = _fetch_ohlcv(ticker, extended_start, end_date)
    if df_ext.empty or len(df_ext) < 210:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note="insufficient data for SMA200")

    sma200 = df_ext['Close'].rolling(200).mean()

    # Slice to start_date
    ts_start = pd.Timestamp(start_date)
    if df_ext.index.tz and ts_start.tz is None:
        ts_start = ts_start.tz_localize('UTC')
    df = df_ext[df_ext.index >= ts_start].copy()
    sma200 = sma200[df_ext.index >= ts_start]

    if df.empty:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note="no data after start_date")

    capital = initial_capital
    trades = wins = 0
    hold_days_list = []
    max_capital = initial_capital
    max_dd = 0.0
    year_caps: dict = {}
    ht_entry_date = None
    ht_shares = 0.0
    idx = 0

    while idx < len(df) - 1:
        s200 = sma200.iloc[idx]
        if pd.isna(s200):
            idx += 1
            continue
        low = float(df['Low'].iloc[idx])
        close = float(df['Close'].iloc[idx])
        if low <= float(s200) and close > float(s200):
            entry_price = float(df['Open'].iloc[idx + 1])
            if entry_price <= 0:
                idx += 1
                continue
            entry_date = df.index[idx + 1]
            if hold_to_end:
                ht_shares = initial_capital / entry_price
                ht_entry_date = entry_date
                exit_price = float(df['Close'].iloc[-1])
                pnl = (exit_price - entry_price) / entry_price * 100
                hold = (df.index[-1] - entry_date).days
                capital *= (1 + pnl / 100)
                trades += 1
                if pnl > 0: wins += 1
                hold_days_list.append(hold)
                break
            else:
                target = entry_price * (1 + profit_target_pct / 100)
                exit_idx = None
                for j in range(idx + 2, len(df)):
                    if df['High'].iloc[j] >= target:
                        exit_idx = j
                        break
                if exit_idx is not None:
                    pnl = profit_target_pct
                    hold = (df.index[exit_idx] - entry_date).days
                    wins += 1
                    idx = exit_idx
                else:
                    pnl = (float(df['Close'].iloc[-1]) - entry_price) / entry_price * 100
                    hold = (df.index[-1] - entry_date).days
                    idx = len(df)
                capital *= (1 + pnl / 100)
                trades += 1
                hold_days_list.append(hold)
                max_capital = max(max_capital, capital)
                max_dd = max(max_dd, (max_capital - capital) / max_capital * 100)
                year_caps[df.index[min(idx, len(df)-1)].year] = capital
        else:
            idx += 1

    if not trades:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note="no SMA200 bounce in period")

    win_rate = round(wins / trades * 100, 1) if trades else 0.0
    avg_hold = round(float(np.mean(hold_days_list)), 1) if hold_days_list else 0.0
    days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    total = round((capital - initial_capital) / initial_capital * 100, 1)
    r = BaselineResult(
        ticker=ticker, label=label,
        start_date=start_date, end_date=end_date,
        initial_capital=initial_capital, final_capital=round(capital, 2),
        total_return_pct=total, annualized_return_pct=_annualized(total, days),
        n_trades=trades, win_rate_pct=win_rate, avg_hold_days=avg_hold,
        max_drawdown_pct=round(max_dd, 1),
        note="Low<=SMA200, Close>SMA200 trigger",
    )
    r.yearly_returns = (_ohlcv_yearly(df, ht_entry_date, ht_shares, initial_capital)
                        if hold_to_end else _yearly_from_caps(year_caps, initial_capital))
    return r


def baseline_golden_cross_entry(ticker: str, start_date: str, end_date: str,
                                 profit_target_pct: float, initial_capital: float,
                                 fast_period: int = 50, slow_period: int = 200,
                                 hold_to_end: bool = False) -> BaselineResult:
    """Classic retail: buy on SMA-50 x SMA-200 golden cross."""
    label_suffix = "Hold" if hold_to_end else f"+{int(profit_target_pct)}%"
    label = f"GoldenCross {label_suffix}"

    extended_start = (pd.Timestamp(start_date) - timedelta(days=310)).strftime('%Y-%m-%d')
    df_ext = _fetch_ohlcv(ticker, extended_start, end_date)
    if df_ext.empty or len(df_ext) < slow_period + 10:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note="insufficient data for golden cross")

    sma_fast = df_ext['Close'].rolling(fast_period).mean()
    sma_slow = df_ext['Close'].rolling(slow_period).mean()

    ts_start = pd.Timestamp(start_date)
    if df_ext.index.tz and ts_start.tz is None:
        ts_start = ts_start.tz_localize('UTC')
    df = df_ext[df_ext.index >= ts_start].copy()
    sma_fast = sma_fast[df_ext.index >= ts_start]
    sma_slow = sma_slow[df_ext.index >= ts_start]

    if df.empty:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note="no data after start_date")

    capital = initial_capital
    trades = wins = 0
    hold_days_list = []
    max_capital = initial_capital
    max_dd = 0.0
    year_caps: dict = {}
    ht_entry_date = None
    ht_shares = 0.0
    idx = 1

    while idx < len(df) - 1:
        f_prev = sma_fast.iloc[idx - 1]
        f_curr = sma_fast.iloc[idx]
        s_prev = sma_slow.iloc[idx - 1]
        s_curr = sma_slow.iloc[idx]
        if any(pd.isna(x) for x in [f_prev, f_curr, s_prev, s_curr]):
            idx += 1
            continue
        if float(f_prev) <= float(s_prev) and float(f_curr) > float(s_curr):
            entry_price = float(df['Open'].iloc[idx + 1])
            if entry_price <= 0:
                idx += 1
                continue
            entry_date = df.index[idx + 1]
            if hold_to_end:
                ht_shares = initial_capital / entry_price
                ht_entry_date = entry_date
                exit_price = float(df['Close'].iloc[-1])
                pnl = (exit_price - entry_price) / entry_price * 100
                hold = (df.index[-1] - entry_date).days
                capital *= (1 + pnl / 100)
                trades += 1
                if pnl > 0: wins += 1
                hold_days_list.append(hold)
                break
            else:
                target = entry_price * (1 + profit_target_pct / 100)
                exit_idx = None
                for j in range(idx + 2, len(df)):
                    if df['High'].iloc[j] >= target:
                        exit_idx = j
                        break
                if exit_idx is not None:
                    pnl = profit_target_pct
                    hold = (df.index[exit_idx] - entry_date).days
                    wins += 1
                    idx = exit_idx
                else:
                    pnl = (float(df['Close'].iloc[-1]) - entry_price) / entry_price * 100
                    hold = (df.index[-1] - entry_date).days
                    idx = len(df)
                capital *= (1 + pnl / 100)
                trades += 1
                hold_days_list.append(hold)
                max_capital = max(max_capital, capital)
                max_dd = max(max_dd, (max_capital - capital) / max_capital * 100)
                year_caps[df.index[min(idx, len(df)-1)].year] = capital
        else:
            idx += 1

    if not trades:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note="no golden cross in period")

    win_rate = round(wins / trades * 100, 1) if trades else 0.0
    avg_hold = round(float(np.mean(hold_days_list)), 1) if hold_days_list else 0.0
    days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    total = round((capital - initial_capital) / initial_capital * 100, 1)
    r = BaselineResult(
        ticker=ticker, label=label,
        start_date=start_date, end_date=end_date,
        initial_capital=initial_capital, final_capital=round(capital, 2),
        total_return_pct=total, annualized_return_pct=_annualized(total, days),
        n_trades=trades, win_rate_pct=win_rate, avg_hold_days=avg_hold,
        max_drawdown_pct=round(max_dd, 1),
        note=f"SMA{fast_period} x SMA{slow_period} cross",
    )
    r.yearly_returns = (_ohlcv_yearly(df, ht_entry_date, ht_shares, initial_capital)
                        if hold_to_end else _yearly_from_caps(year_caps, initial_capital))
    return r


def baseline_volume_surge(ticker: str, start_date: str, end_date: str,
                           profit_target_pct: float, initial_capital: float,
                           volume_multiplier: float = 2.0,
                           hold_to_end: bool = False) -> BaselineResult:
    """Institutional signal: buy on volume spike above N x 20-day average."""
    label_suffix = "Hold" if hold_to_end else f"+{int(profit_target_pct)}%"
    label = f"VolSurge {label_suffix}"

    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty or len(df) <= 22:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note="no volume surge in period")

    avg_vol = df['Volume'].rolling(20).mean()
    capital = initial_capital
    trades = wins = 0
    hold_days_list = []
    max_capital = initial_capital
    max_dd = 0.0
    year_caps: dict = {}
    ht_entry_date = None
    ht_shares = 0.0
    idx = 20

    while idx < len(df) - 1:
        av = avg_vol.iloc[idx]
        if pd.isna(av) or float(av) <= 0:
            idx += 1
            continue
        if float(df['Volume'].iloc[idx]) >= volume_multiplier * float(av):
            entry_price = float(df['Open'].iloc[idx + 1])
            if entry_price <= 0:
                idx += 1
                continue
            entry_date = df.index[idx + 1]
            if hold_to_end:
                ht_shares = initial_capital / entry_price
                ht_entry_date = entry_date
                exit_price = float(df['Close'].iloc[-1])
                pnl = (exit_price - entry_price) / entry_price * 100
                hold = (df.index[-1] - entry_date).days
                capital *= (1 + pnl / 100)
                trades += 1
                if pnl > 0: wins += 1
                hold_days_list.append(hold)
                break
            else:
                target = entry_price * (1 + profit_target_pct / 100)
                exit_idx = None
                for j in range(idx + 2, len(df)):
                    if df['High'].iloc[j] >= target:
                        exit_idx = j
                        break
                if exit_idx is not None:
                    pnl = profit_target_pct
                    hold = (df.index[exit_idx] - entry_date).days
                    wins += 1
                    idx = exit_idx
                else:
                    pnl = (float(df['Close'].iloc[-1]) - entry_price) / entry_price * 100
                    hold = (df.index[-1] - entry_date).days
                    idx = len(df)
                capital *= (1 + pnl / 100)
                trades += 1
                hold_days_list.append(hold)
                max_capital = max(max_capital, capital)
                max_dd = max(max_dd, (max_capital - capital) / max_capital * 100)
                year_caps[df.index[min(idx, len(df)-1)].year] = capital
        else:
            idx += 1

    if not trades:
        return _baseline_result(ticker, label, start_date, end_date,
                                initial_capital, initial_capital,
                                note="no volume surge in period")

    win_rate = round(wins / trades * 100, 1) if trades else 0.0
    avg_hold = round(float(np.mean(hold_days_list)), 1) if hold_days_list else 0.0
    days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    total = round((capital - initial_capital) / initial_capital * 100, 1)
    r = BaselineResult(
        ticker=ticker, label=label,
        start_date=start_date, end_date=end_date,
        initial_capital=initial_capital, final_capital=round(capital, 2),
        total_return_pct=total, annualized_return_pct=_annualized(total, days),
        n_trades=trades, win_rate_pct=win_rate, avg_hold_days=avg_hold,
        max_drawdown_pct=round(max_dd, 1),
        note=f"volume >= {volume_multiplier:.0f}x 20d avg",
    )
    r.yearly_returns = (_ohlcv_yearly(df, ht_entry_date, ht_shares, initial_capital)
                        if hold_to_end else _yearly_from_caps(year_caps, initial_capital))
    return r


def baseline_sniper_hold(ticker: str, start_date: str, end_date: str,
                          initial_capital: float) -> BaselineResult:
    """Sniper entry quality: run Sniper at start, wait up to 90 days for L1 hit, hold to end."""
    from sniper import TechSniperAI
    df = _fetch_ohlcv(ticker, start_date, end_date)
    if df.empty:
        return _baseline_result(ticker, "Sniper Hold", start_date, end_date,
                                initial_capital, initial_capital, note="no data")
    try:
        bot = TechSniperAI(ticker, as_of_date=start_date, use_cache=True)
        if bot.current_price == 0:
            return _baseline_result(ticker, "Sniper Hold", start_date, end_date,
                                    initial_capital, initial_capital, note="sniper price=0")
        orders = bot.generate_orders()
    except Exception as e:
        return _baseline_result(ticker, "Sniper Hold", start_date, end_date,
                                initial_capital, initial_capital, note=f"sniper err: {e}")

    if not orders:
        return _baseline_result(ticker, "Sniper Hold", start_date, end_date,
                                initial_capital, initial_capital, note="no levels generated")

    levels = sorted([v['price'] for v in orders.values()], reverse=True)
    l1 = levels[0]

    ts_start = pd.Timestamp(start_date)
    if df.index.tz and ts_start.tz is None:
        ts_start = ts_start.tz_localize('UTC')
    window = df[df.index >= ts_start].iloc[:90]  # 90-day entry window

    entry_date = None
    entry_price = None
    for i in range(len(window)):
        if float(window['Low'].iloc[i]) <= l1:
            entry_price = min(float(window['Open'].iloc[i]), l1)
            entry_date = window.index[i]
            break

    if entry_price is None:
        return _baseline_result(ticker, "Sniper Hold", start_date, end_date,
                                initial_capital, initial_capital,
                                note=f"L1={l1:.2f} never hit in 90d")

    shares = initial_capital / entry_price
    exit_price = float(df['Close'].iloc[-1])
    final = shares * exit_price
    hold = (df.index[-1] - entry_date).days

    # max drawdown from entry to end
    entry_ts = entry_date
    held = df[df.index >= entry_ts]
    peak, max_dd = entry_price, 0.0
    for c in held['Close'].values:
        if c > peak: peak = c
        dd = (peak - c) / peak * 100
        if dd > max_dd: max_dd = dd

    days_total = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    total = round((final - initial_capital) / initial_capital * 100, 1)
    r = _baseline_result(ticker, "Sniper Hold", start_date, end_date,
                         initial_capital, final, 1, 100.0 if final >= initial_capital else 0.0,
                         hold, round(max_dd, 1),
                         f"L1={l1:.2f}, entered {entry_date.strftime('%Y-%m-%d')}")
    r.yearly_returns = _ohlcv_yearly(held, entry_date, shares, initial_capital)
    return r


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
                # Hold Forever group
                baselines.append(baseline_buy_hold(ticker, start, end_date, initial_capital))
                baselines.append(baseline_ticker_dca(ticker, start, end_date, initial_capital))
                baselines.append(baseline_spy_dca(start, end_date, initial_capital))
                baselines.append(baseline_sniper_hold(ticker, start, end_date, initial_capital))
                baselines.append(baseline_breakout_entry(ticker, start, end_date, 0, initial_capital, hold_to_end=True))
                baselines.append(baseline_rsi_entry(ticker, start, end_date, 0, initial_capital, hold_to_end=True))
                baselines.append(baseline_sma200_bounce(ticker, start, end_date, 0, initial_capital, hold_to_end=True))
                baselines.append(baseline_golden_cross_entry(ticker, start, end_date, 0, initial_capital, hold_to_end=True))
                baselines.append(baseline_volume_surge(ticker, start, end_date, 0, initial_capital, hold_to_end=True))
                # Re-enter group (per profit target)
                for target in targets:
                    baselines.append(baseline_immediate_rebuy(ticker, start, end_date, target, initial_capital))
                    baselines.append(baseline_random_entry(ticker, start, end_date, target, initial_capital))
                    baselines.append(baseline_pullback_entry(ticker, start, end_date, target, initial_capital))
                    baselines.append(baseline_dca_with_exit(ticker, start, end_date, target, initial_capital))
                    baselines.append(baseline_breakout_entry(ticker, start, end_date, target, initial_capital))
                    baselines.append(baseline_rsi_entry(ticker, start, end_date, target, initial_capital))
                    baselines.append(baseline_sma200_bounce(ticker, start, end_date, target, initial_capital))
                    baselines.append(baseline_golden_cross_entry(ticker, start, end_date, target, initial_capital))
                    baselines.append(baseline_volume_surge(ticker, start, end_date, target, initial_capital))
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

    # ── HOLD FOREVER GROUP ────────────────────────────────────────────────
    tbl.add_section()
    tbl.add_row("[bold dim]── HOLD FOREVER (same exit: period end) ──[/bold dim]",
                "", "", "", "", "", "", "", "")
    hold_forever_rows = [
        ("Buy & Hold",          "Buy&Hold",          "dim"),
        (f"DCA {ticker}",       "DCA",               "dim"),
        ("SPY DCA",             "SPY DCA",            "dim"),
        ("Sniper Hold",         "Sniper Hold",        "bold cyan"),
        ("Breakout 20d Hold",   "Breakout20d Hold",   "blue"),
        ("RSI>50 Hold",         "RSI>50 Hold",        "blue"),
        ("SMA200 Bounce Hold",  "SMA200Bounce Hold",  "blue"),
        ("Golden Cross Hold",   "GoldenCross Hold",   "blue"),
        ("Vol Surge Hold",      "VolSurge Hold",      "blue"),
    ]
    for row_label, blabel, style in hold_forever_rows:
        b = next((x for x in baselines if x.label == blabel), None)
        if b:
            _row(row_label, b.total_return_pct, b.annualized_return_pct,
                 b.final_capital, b.n_trades, b.win_rate_pct, b.avg_hold_days,
                 b.max_drawdown_pct, b.note, style)

    # ── RE-ENTER GROUP (per target) ───────────────────────────────────────
    for target in targets:
        tbl.add_section()
        tbl.add_row(f"[bold dim]── SELL +{int(target)}%, RE-ENTER ──[/bold dim]",
                    "", "", "", "", "", "", "", "")
        reenter_rows = [
            (f"Immediate Rebuy +{int(target)}%",  f"ImmediateRebuy+{int(target)}%", "yellow"),
            (f"Random entry +{int(target)}%",     f"Random+{int(target)}%",         "yellow"),
            (f"Pullback -5% +{int(target)}%",     f"Pullback+{int(target)}%",       "yellow"),
            (f"DCA +{int(target)}%",              f"DCA+{int(target)}%",            "yellow"),
            (f"Breakout 20d +{int(target)}%",     f"Breakout20d +{int(target)}%",   "magenta"),
            (f"RSI>50 +{int(target)}%",           f"RSI>50 +{int(target)}%",        "magenta"),
            (f"SMA200 Bounce +{int(target)}%",    f"SMA200Bounce +{int(target)}%",  "magenta"),
            (f"Golden Cross +{int(target)}%",     f"GoldenCross +{int(target)}%",   "magenta"),
            (f"Vol Surge +{int(target)}%",        f"VolSurge +{int(target)}%",      "magenta"),
        ]
        for row_label, blabel, style in reenter_rows:
            b = next((x for x in baselines if x.label == blabel), None)
            if b:
                _row(row_label, b.total_return_pct, b.annualized_return_pct,
                     b.final_capital, b.n_trades, b.win_rate_pct, b.avg_hold_days,
                     b.max_drawdown_pct, b.note, style)

    console.print(tbl)
    _print_yearly_table(ticker, start, end, sniper_results, baselines, targets)


def _print_yearly_table(ticker, start, end, sniper_results, baselines, targets):
    """Show calendar-year return for each strategy — spot regime changes at a glance."""
    # Collect all years present across all strategies
    all_yearly: list[tuple[str, dict, str]] = []  # (label, yearly_dict, style)

    for r in sniper_results:
        if hasattr(r, 'trades') and r.trades:
            yc: dict = {}
            cap = r.initial_capital
            for t in r.trades:
                exit_yr = pd.Timestamp(t.exit_date).year if t.exit_date else None
                if exit_yr:
                    cap *= (1 + t.pnl_pct / 100)
                    yc[exit_yr] = cap
            yr_ret = _yearly_from_caps(yc, r.initial_capital)
        else:
            yr_ret = {}
        all_yearly.append((f"Sniper {r.strategy}", yr_ret, "bold cyan"))

    hold_labels = [
        ("Buy&Hold", "dim"), ("DCA", "dim"), ("SPY DCA", "dim"),
        ("Sniper Hold", "bold cyan"),
        ("Breakout20d Hold", "blue"), ("RSI>50 Hold", "blue"),
        ("SMA200Bounce Hold", "blue"), ("GoldenCross Hold", "blue"),
        ("VolSurge Hold", "blue"),
    ]
    for blabel, style in hold_labels:
        b = next((x for x in baselines if x.label == blabel), None)
        if b and b.yearly_returns:
            all_yearly.append((blabel, b.yearly_returns, style))

    for target in targets:
        reenter_labels = [
            (f"ImmediateRebuy+{int(target)}%", "yellow"),
            (f"Pullback+{int(target)}%", "yellow"),
            (f"DCA+{int(target)}%", "yellow"),
            (f"Breakout20d +{int(target)}%", "magenta"),
            (f"RSI>50 +{int(target)}%", "magenta"),
            (f"VolSurge +{int(target)}%", "magenta"),
        ]
        for blabel, style in reenter_labels:
            b = next((x for x in baselines if x.label == blabel), None)
            if b and b.yearly_returns:
                all_yearly.append((blabel, b.yearly_returns, style))

    if not all_yearly:
        return

    years = sorted({yr for _, yd, _ in all_yearly for yr in yd})
    if not years:
        return

    tbl = Table(title=f"Year-by-Year Returns: {ticker}  {start} -> {end}",
                box=box.SIMPLE_HEAD, header_style="bold", show_header=True)
    tbl.add_column("Strategy", min_width=24)
    for yr in years:
        tbl.add_column(str(yr), justify="right", min_width=8)

    for label, yd, style in all_yearly:
        cells = []
        for yr in years:
            if yr in yd:
                v = yd[yr]
                color = "green" if v >= 0 else "red"
                cells.append(f"[{color}]{v:+.0f}%[/{color}]")
            else:
                cells.append("[dim]—[/dim]")
        tbl.add_row(f"[{style}]{label}[/{style}]", *cells)

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

    # ── Hold Forever baselines ────────────────────────────────────────────
    tbl.add_section()
    tbl.add_row("[bold dim]── HOLD FOREVER ──[/bold dim]",
                "", "", "", "", "", "", "", "")
    hold_labels = [
        ("Buy&Hold",         "dim"),
        ("DCA",              "dim"),
        ("SPY DCA",          "dim"),
        ("Sniper Hold",      "bold cyan"),
        ("Breakout20d Hold", "blue"),
        ("RSI>50 Hold",      "blue"),
        ("SMA200Bounce Hold","blue"),
        ("GoldenCross Hold", "blue"),
        ("VolSurge Hold",    "blue"),
    ]
    for blabel, style in hold_labels:
        bucket = [b for b in all_baselines if b.label == blabel]
        if not bucket:
            continue
        avg_ret = np.mean([b.total_return_pct for b in bucket])
        avg_ann = np.mean([b.annualized_return_pct for b in bucket])
        avg_dd  = np.mean([b.max_drawdown_pct for b in bucket])
        rc = "green" if avg_ret >= 0 else "red"
        tbl.add_row(
            f"[{style}]{blabel}[/{style}]",
            f"[{rc}]{avg_ret:+.1f}%[/{rc}]",
            f"[{rc}]{avg_ann:+.1f}%[/{rc}]",
            "-", "-", "-",
            f"{avg_dd:.1f}%", "-", "-",
        )

    # ── Re-enter baselines ────────────────────────────────────────────────
    tbl.add_section()
    tbl.add_row("[bold dim]── RE-ENTER AT TARGET ──[/bold dim]",
                "", "", "", "", "", "", "", "")
    for t in targets:
        reenter_labels = [
            (f"ImmediateRebuy+{int(t)}%", "yellow"),
            (f"Random+{int(t)}%",         "yellow"),
            (f"Pullback+{int(t)}%",       "yellow"),
            (f"DCA+{int(t)}%",            "yellow"),
            (f"Breakout20d +{int(t)}%",   "magenta"),
            (f"RSI>50 +{int(t)}%",        "magenta"),
            (f"SMA200Bounce +{int(t)}%",  "magenta"),
            (f"GoldenCross +{int(t)}%",   "magenta"),
            (f"VolSurge +{int(t)}%",      "magenta"),
        ]
        for blabel, style in reenter_labels:
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
                f"[{style}]{blabel}[/{style}]",
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
DEFAULT_TARGETS = [5.0, 10.0, 25.0, 50.0]
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
