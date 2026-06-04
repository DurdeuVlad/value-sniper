"""
Value Sniper — CLI sister to the Streamlit dashboard.
Identical functionality, terminal output.

Usage:
  python src/cli.py MSFT
  python src/cli.py MSFT --ai --ml --ml-device cuda
  python src/cli.py MSFT --backtest --start 2023-01-01 --end 2024-12-31 --forward 60
  python src/cli.py MSFT --date 2024-06-01 --forward 60   (single historical point)
  python src/cli.py MSFT --plot
"""

import argparse
import os
import sys
import io

# Force UTF-8 output on Windows so rich can render box-drawing chars
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from rich.text import Text
from rich.rule import Rule
import pandas as pd

console = Console(highlight=False, emoji=False)


# ─── helpers ────────────────────────────────────────────────────────────────

def _color_hit(hit: bool) -> str:
    return "[green]HIT[/green]" if hit else "[red]miss[/red]"


def _level_color(i: int) -> str:
    return ["cyan", "yellow", "red"][i]


def _pct_color(pct: float) -> str:
    if pct < 5:
        return "green"
    if pct < 15:
        return "yellow"
    return "red"


# ─── live analysis ──────────────────────────────────────────────────────────

def run_analysis(args):
    from sniper import TechSniperAI
    from llm.gemini import GeminiProvider
    from ml.timesfm_signal import TimesFMSignal, is_available as timesfm_available

    as_of = getattr(args, 'date', None)
    historical = bool(as_of)

    # AI provider
    ai_provider = None
    if args.ai:
        try:
            ai_provider = GeminiProvider()
        except ValueError as e:
            console.print(f"[red][ERROR] Cannot enable AI: {e}[/red]")
            sys.exit(1)

    # ML signal
    ml_signal = None
    if args.ml:
        if not timesfm_available():
            console.print("[red][ERROR] TimesFM not installed. Run: pip install -r requirements-ml.txt[/red]")
            sys.exit(1)
        ml_signal = TimesFMSignal(device=args.ml_device)

    mode_tag = f" [dim](historical: {as_of})[/dim]" if historical else ""
    console.print(Rule(f"[bold cyan]VALUE SNIPER — {args.ticker.upper()}{mode_tag}[/bold cyan]"))

    bot = TechSniperAI(
        args.ticker,
        use_cache=not args.no_cache,
        llm_provider=ai_provider,
        as_of_date=as_of,
    )

    if bot.current_price == 0:
        console.print("[red]Failed to fetch data.[/red]")
        return

    orders = bot.generate_orders(ml_signal=ml_signal)
    if not orders:
        console.print("[red]No orders generated.[/red]")
        return

    # ── price header ──
    console.print()
    console.print(Panel(
        f"[bold white]{args.ticker.upper()}[/bold white]  "
        f"[bold green]${bot.current_price:.2f}[/bold green]",
        title="Current Price", expand=False
    ))

    # ── support levels table ──
    tbl = Table(title="Support Levels", box=box.ROUNDED, show_header=True, header_style="bold")
    tbl.add_column("Level", style="bold", min_width=28)
    tbl.add_column("Price", justify="right", min_width=10)
    tbl.add_column("Drop %", justify="right", min_width=8)
    tbl.add_column("Est P/E", justify="right", min_width=8)
    tbl.add_column("Est P/S", justify="right", min_width=8)
    tbl.add_column("Allocate", min_width=16)
    tbl.add_column("Zone", min_width=38)

    for i, (label, v) in enumerate(orders.items()):
        c = _level_color(i)
        drop_c = _pct_color(v['percent_drop'])
        tbl.add_row(
            f"[{c}]{label}[/{c}]",
            f"[{c}]${v['price']:.2f}[/{c}]",
            f"[{drop_c}]-{v['percent_drop']:.1f}%[/{drop_c}]",
            f"{v['estimated_pe']:.1f}",
            f"{v['estimated_ps']:.1f}",
            v['position_size'],
            f"[dim]{v['possibility']}[/dim]",
        )

    console.print(tbl)

    # ── protocol log panels ──
    console.print()
    console.print(Rule("[dim]Protocol Log[/dim]"))

    log_items = [
        (k, v) for k, v in bot.runtime_log.items()
        if k not in ('FINAL ORDERS', 'Recommendation', 'No-Trade Warning', 'Analysis Date')
    ]
    panels = []
    for k, v in log_items:
        color = "green" if any(x in str(v).upper() for x in ['STRONG', 'HEALTHY', 'NEUTRAL', 'FAIR']) else \
                "yellow" if any(x in str(v).upper() for x in ['WEAK', 'CAUTION', 'SKIPPED']) else \
                "red" if any(x in str(v).upper() for x in ['WARNING', 'BEAR', 'FEAR', 'OVERBOUGHT']) else "white"
        panels.append(Panel(f"[{color}]{v}[/{color}]", title=f"[bold]{k}[/bold]", expand=True))

    # print in rows of 2
    for i in range(0, len(panels), 2):
        row = panels[i:i+2]
        console.print(Columns(row, equal=True, expand=True))

    # ── recommendation / warnings ──
    console.print()
    if 'No-Trade Warning' in bot.runtime_log:
        console.print(Panel(f"[bold red]{bot.runtime_log['No-Trade Warning']}[/bold red]", title="WARNING"))
    if 'Recommendation' in bot.runtime_log:
        console.print(Panel(f"[bold green]{bot.runtime_log['Recommendation']}[/bold green]", title="Recommendation"))

    # ── AI report ──
    if args.ai:
        console.print()
        console.print(Rule("[bold magenta]AI Strategic Analysis (Gemini)[/bold magenta]"))

        def cli_cb(msg):
            console.print(f"[dim][AI] {msg}[/dim]", end="\r")

        report = bot.run_full_analysis(orders, progress_callback=cli_cb)
        console.print()
        if report and 'strategic_analysis' in report:
            sa = report['strategic_analysis']
            if isinstance(sa, dict):
                for section, text in sa.items():
                    console.print(Panel(str(text), title=f"[magenta]{section}[/magenta]"))
            else:
                console.print(Panel(str(sa), title="Strategic Analysis"))

    # ── plot ──
    if args.plot:
        from visualization import SniperPlotter
        bot.runtime_log['FINAL ORDERS'] = orders
        plotter = SniperPlotter(bot)
        plotter.log_steps(bot.runtime_log)
        plotter.plot_sniper_view({k: v['price'] for k, v in orders.items()})
        console.print("[green]Charts saved to _runtime/[/green]")

    console.print()


# ─── backtest ───────────────────────────────────────────────────────────────

def run_backtest(args):
    from backtest import Backtester, generate_monthly_dates, BacktestResult
    from dataclasses import fields

    ticker = args.ticker.upper()
    end = args.end or pd.Timestamp.now().strftime('%Y-%m-%d')
    dates = generate_monthly_dates(args.start, end)

    console.print(Rule(f"[bold cyan]BACKTEST — {ticker}[/bold cyan]"))
    console.print(f"  Dates: [cyan]{args.start}[/cyan] to [cyan]{end}[/cyan]  ({len(dates)} months)")
    console.print(f"  Forward window: [cyan]{args.forward} days[/cyan]")
    console.print(f"  Hit rule: intraday Low <= level\n")

    bt = Backtester(ticker, forward_days=args.forward, verbose=False)

    results = []
    with console.status(f"[cyan]Running {len(dates)} dates...[/cyan]") as status:
        for i, date in enumerate(dates):
            status.update(f"[cyan][{i+1}/{len(dates)}] {date}...[/cyan]")
            r = bt.run_single(date)
            if r:
                results.append(r)

    if not results:
        console.print("[red]No results.[/red]")
        return

    # ── results table ──
    tbl = Table(title=f"{ticker} Backtest Results", box=box.ROUNDED, header_style="bold")
    tbl.add_column("Date", min_width=12)
    tbl.add_column("Price", justify="right", min_width=9)
    tbl.add_column("L1", justify="right", min_width=9)
    tbl.add_column("L2", justify="right", min_width=9)
    tbl.add_column("L3", justify="right", min_width=9)
    tbl.add_column("L1 Hit", justify="center", min_width=8)
    tbl.add_column("L2 Hit", justify="center", min_width=8)
    tbl.add_column("L3 Hit", justify="center", min_width=8)
    tbl.add_column("Drawdown", justify="right", min_width=10)

    for r in results:
        tbl.add_row(
            r.analysis_date,
            f"${r.price_at_analysis:.2f}",
            f"[cyan]${r.level_1_price:.2f}[/cyan]",
            f"[yellow]${r.level_2_price:.2f}[/yellow]",
            f"[red]${r.level_3_price:.2f}[/red]",
            _color_hit(r.l1_hit),
            _color_hit(r.l2_hit),
            _color_hit(r.l3_hit),
            f"{r.max_drawdown_pct:.1f}%",
        )

    console.print(tbl)

    # ── summary ──
    summary = bt.summarize(results)
    console.print()

    summary_tbl = Table(title="Summary", box=box.SIMPLE, show_header=False)
    summary_tbl.add_column("Metric", style="bold", min_width=24)
    summary_tbl.add_column("Value", justify="right")

    color_map = {'l1': 'cyan', 'l2': 'yellow', 'l3': 'red'}
    labels = {
        'total_dates': ('Dates analysed', 'white'),
        'l1_hit_rate': ('L1 Hit Rate (Dip)', 'cyan'),
        'l2_hit_rate': ('L2 Hit Rate (Deep Value)', 'yellow'),
        'l3_hit_rate': ('L3 Hit Rate (Bear Market)', 'red'),
        'l1_avg_days': ('L1 Avg Days to Hit', 'cyan'),
        'l2_avg_days': ('L2 Avg Days to Hit', 'yellow'),
        'l3_avg_days': ('L3 Avg Days to Hit', 'red'),
        'avg_max_drawdown': ('Avg Max Drawdown', 'white'),
    }
    for key, (label, color) in labels.items():
        val = summary.get(key)
        if val is not None:
            summary_tbl.add_row(label, f"[{color}]{val}[/{color}]")

    console.print(summary_tbl)

    # ── CSV export ──
    start_str = args.start.replace('-', '')
    end_str = end.replace('-', '')
    out_dir = os.path.join(os.path.dirname(__file__), '..', '_runtime')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.normpath(os.path.join(out_dir, f"{ticker}_backtest_{start_str}_{end_str}.csv"))
    bt.export_csv(results, out_path)
    console.print(f"[green]CSV → {out_path}[/green]")
    console.print()


# ─── single historical point ─────────────────────────────────────────────────

def run_historical_point(args):
    """Single date: run analysis + show what happened in the forward window."""
    from backtest import Backtester

    ticker = args.ticker.upper()
    console.print(Rule(f"[bold cyan]HISTORICAL POINT — {ticker} @ {args.date}[/bold cyan]"))

    bt = Backtester(ticker, forward_days=args.forward, verbose=False)

    with console.status(f"[cyan]Running analysis for {args.date}...[/cyan]"):
        r = bt.run_single(args.date)

    if not r:
        console.print("[red]No result.[/red]")
        return

    console.print(Panel(
        f"[bold white]{ticker}[/bold white] on [cyan]{r.analysis_date}[/cyan]  "
        f"Price: [bold green]${r.price_at_analysis:.2f}[/bold green]",
        expand=False
    ))

    tbl = Table(box=box.ROUNDED, header_style="bold", show_header=True)
    tbl.add_column("Level", min_width=8)
    tbl.add_column("Price", justify="right")
    tbl.add_column("Drop %", justify="right")
    tbl.add_column(f"Hit? ({args.forward}d)", justify="center")
    tbl.add_column("Days to Hit", justify="right")

    rows = [
        ("L1 (Dip)", r.level_1_price, r.l1_pct_drop, r.l1_hit, r.l1_days_to_hit, "cyan"),
        ("L2 (Deep)", r.level_2_price, r.l2_pct_drop, r.l2_hit, r.l2_days_to_hit, "yellow"),
        ("L3 (Bear)", r.level_3_price, r.l3_pct_drop, r.l3_hit, r.l3_days_to_hit, "red"),
    ]
    for label, price, drop, hit, days, color in rows:
        tbl.add_row(
            f"[{color}]{label}[/{color}]",
            f"[{color}]${price:.2f}[/{color}]",
            f"-{drop:.1f}%",
            _color_hit(hit),
            str(days) if days is not None else "—",
        )

    console.print(tbl)
    console.print(f"\n  Max drawdown in {args.forward}-day window: [bold]{r.max_drawdown_pct:.1f}%[/bold]")
    if r.notes and r.notes != 'ok':
        console.print(f"  [dim]Notes: {r.notes}[/dim]")
    console.print()


# ─── main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Value Sniper CLI — full dashboard functionality in the terminal',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/cli.py MSFT                                      Live analysis
  python src/cli.py MSFT --ai --ml --ml-device cuda           With Gemini AI + TimesFM GPU
  python src/cli.py MSFT --plot                               + save charts to _runtime/
  python src/cli.py MSFT --date 2024-06-01 --forward 60       Single historical point
  python src/cli.py MSFT --backtest --start 2023-01-01 \\
         --end 2024-12-31 --forward 60                        Full backtest range
        """
    )

    parser.add_argument('ticker', type=str, help='Stock ticker (e.g. MSFT, NVDA)')

    # analysis flags
    parser.add_argument('--no-cache', action='store_true', help='Ignore cache, fetch live data')
    parser.add_argument('--ai', action='store_true', help='Enable Gemini AI analysis (needs GEMINI_API_KEY)')
    parser.add_argument('--ml', action='store_true', help='Enable TimesFM ML signal (Protocol J)')
    parser.add_argument('--ml-device', type=str, default='auto', choices=['auto', 'cpu', 'cuda'],
                        help='Device for TimesFM (default: auto)')
    parser.add_argument('--plot', action='store_true', help='Save charts to _runtime/')

    # historical / backtest flags
    parser.add_argument('--date', type=str, default=None,
                        help='Single historical date YYYY-MM-DD (runs point-in-time analysis)')
    parser.add_argument('--forward', type=int, default=60,
                        help='Forward window in days for historical/backtest (default: 60)')
    parser.add_argument('--backtest', action='store_true', help='Run full backtest over a date range')
    parser.add_argument('--start', type=str, default=None, help='Backtest start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, default=None, help='Backtest end date YYYY-MM-DD (default: today)')

    args = parser.parse_args()

    if args.backtest:
        if not args.start:
            parser.error("--backtest requires --start")
        run_backtest(args)
    elif args.date:
        run_historical_point(args)
    else:
        run_analysis(args)
