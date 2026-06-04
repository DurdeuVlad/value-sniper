<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" />
  <img src="https://img.shields.io/badge/Streamlit-Dashboard-red?style=flat-square&logo=streamlit" />
  <img src="https://img.shields.io/badge/AI-Gemini%202.5-orange?style=flat-square&logo=google" />
  <img src="https://img.shields.io/badge/ML-TimesFM%202.5-purple?style=flat-square&logo=tensorflow" />
</p>

<h1 align="center">Value Sniper</h1>
<p align="center"><strong>Quantitative entry system for Nasdaq-100 tech equities</strong></p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="STRATEGY.md">Strategy</a> ·
  <a href="RESEARCH.md">Research</a> ·
  <a href="docs/sniper_architecture.md">Architecture</a> ·
  <a href="docs/visualization_guide.md">Charts</a> ·
  <a href="AGENT.md">Agent Install</a>
</p>

---

Most people who lose money in stocks don't pick bad companies. They buy at the wrong price, have no thesis for why that price is defensible, and panic-sell when it falls further.

Value Sniper is built around one idea: **you should never enter a position without knowing why the price level is structurally sound.** Every level the system outputs is backed by nine independent signals drawn from options market microstructure, macro regime data, institutional gap analysis, and market breadth. When they converge, you have a real reason to be there. When they don't, the system tells you to wait.

The result is not a magic return generator. It is a tool that removes investor anxiety. It converts *"I hope this holds"* into *"I know why this should hold"* and that change in certainty changes everything about how you hold a position through volatility. Every entry has a documented thesis. You know the floor. You know what breaks the trade. The uncertainty that causes panic-selling disappears.

---

## Quick Start

```bash
git clone https://github.com/DurdeuVlad/value-sniper
cd value-sniper
pip install -r requirements.txt
streamlit run src/dashboard.py
```

Opens at `http://localhost:8501`. That's it.

---

## How It Works

The system analyses a ticker and outputs three support levels: a dip entry, a deep value level, and a bear market floor. Each level is the result of K-Means clustering across nine independent signals:

| # | Protocol | Signal Source |
|---|---|---|
| A | **Macro Regime** | 10Y Treasury yield vs Bollinger Bands. Are rates in stress territory? |
| B | **Gamma Regime** | VIX level. Is the market pricing fear, demanding wider margins? |
| C | **Options Max Pain** | The strike where options market makers suffer maximum loss |
| D | **Gap Analysis** | Unfilled institutional breakaway gaps, weighted by age |
| E | **Sector Strength** | XLK/SPY ratio. Is tech outperforming or breaking down? |
| F | **Momentum** | RSI-14. Overbought, oversold, or neutral? |
| G | **Valuation Regime** | P/S ratio vs sector average. Is a premium priced in? |
| H | **Market Breadth** | SPY vs RSP divergence. Broad move or narrow leadership? |
| I | **Trend Strength** | ADX-14. Trending or choppy range? |
| J | **TimesFM ML** *(optional)* | Google's foundation model 20-day probabilistic price floor |

The system also includes a **Defensive Shift** mechanism. When sector breakdown, narrow breadth, or macro stress is detected, Level 1 is deleted and all levels are pushed lower. It is saying: *normal dip-buying logic does not apply right now.*

---

## Results

Full research and detailed findings in [RESEARCH.md](RESEARCH.md).

The benchmark compares Value Sniper against 14 other entry strategies across two test groups:

- **Hold Forever** — one entry, hold to period end. Tests pure entry quality.
- **Sell at +X%, Re-enter** — systematic compound cycling at +10%, +25%, +50%. Tests whether entry timing adds alpha over a full cycle.

### Bear entry test: Jan 2022 → Jun 2026 (AAPL + MSFT)

Entering at the 2022 market peak and holding through the full bear-to-recovery cycle is the hardest scenario. Here are the average returns across both tickers:

| Strategy | Avg Return | Annualised | vs Buy & Hold |
|---|---|---|---|
| **Sniper +25%** | **+144.3%** | **+21.8%** | **+84.8pp** |
| Vol Surge Hold | +99.2% | +16.6% | +39.7pp |
| Sniper +50% | +94.0% | +15.9% | +34.5pp |
| SMA200 Bounce +25% | +92.8% | +15.4% | +33.3pp |
| Golden Cross Hold | +88.0% | +15.3% | +28.5pp |
| **Sniper Hold** | **+71.0%** | **+12.8%** | **+11.5pp** |
| Buy & Hold | +59.5% | +11.0% | baseline |
| SPY DCA | +56.3% | +10.6% | -3.2pp |
| DCA same ticker | +47.7% | +9.1% | -11.8pp |
| **Sniper +10%** | **+28.2%** | **+5.6%** | **-31.3pp** |

### What the data says

**Sniper +25% is the standout result** at +144.3% average — 2.4× Buy & Hold, best of every strategy tested. The combination of a structurally-defended L1 entry and a 25% exit target captures the full bounce from the 2022 floor without exiting too early or staying in cash too long.

**Sniper Hold beats Buy & Hold by +11.5pp** (+71% vs +59.5%). Same exit date, same stock — the only difference is the entry price. The L1 entry during the 2022 drawdown produced a lower cost basis that compounded over four years into a real, consistent advantage. This held on both AAPL (+95.4% vs +79.5%) and MSFT (+46.6% vs +39.4%).

**Sniper +10% badly underperforms Buy & Hold** (+28.2% vs +59.5%). The yearly table explains this: the +10% target exits the position quickly, the system goes to cash waiting for the next L1 signal, and the stock recovers 49-58% without offering another support entry. Cash drag from tight targets destroys the compounding advantage. The system is designed for meaningful structural dips — a +10% target does not exploit the full bounce.

**Vol Surge Hold is the strongest technical baseline** at +99.2%. Volume spikes ≥ 2× 20-day average mark institutional accumulation events that happen to coincide with major panic selloffs. It entered lower and earlier in 2022 than most other strategies, absorbing only -4% in 2022 (AAPL) vs -26% for Buy & Hold.

**The 2022 drawdown is the decisive variable.** Yearly returns show all calendar-entry strategies (Buy & Hold, DCA) took -26% to -28% in 2022. Sniper Hold entered after the L1 hit — smaller drawdown, lower cost basis. Sniper +25/50% was in cash during 2022's decline (shown as `—` in the yearly table) and entered at the structural floor.

### The honest tradeoff

When price goes straight up without touching a support level, the Sniper has no position. In sustained uptrends that never dip to structural support, momentum strategies (Breakout, Vol Surge, RSI cross) outperform because they don't wait.

This is the design, not a flaw. The system is a precision entry tool for patient capital with a structural thesis. It is not for catching every move.

See [RESEARCH.md](RESEARCH.md) for full tables, year-by-year evolution, and complete analysis.

---

## Disclaimer

> **This software is for educational and research purposes only. It does not constitute financial advice, investment advice, or a recommendation to buy or sell any security. All backtested results are historical and do not guarantee future performance. You are solely responsible for your own investment decisions. Trading stocks involves significant risk of loss.**

---

## Installation

**Requirements:** Python 3.10+

```bash
git clone https://github.com/DurdeuVlad/value-sniper
cd value-sniper
pip install -r requirements.txt
```

Copy the env template (optional, only needed for AI analysis):
```bash
# Linux / macOS / Git Bash
cp .env.example .env

# Windows Command Prompt
copy .env.example .env
```

Open `.env` and add your `GEMINI_API_KEY` if you want Gemini AI summaries.

---

## Usage

### Dashboard

```bash
streamlit run src/dashboard.py
```

Opens at `http://localhost:8501`. Select a ticker, run the analysis, explore evidence tabs for every protocol, run backtests, export reports.

### CLI

```bash
# Live analysis with full protocol breakdown
python src/cli.py MSFT

# With AI strategic summary (requires GEMINI_API_KEY in .env)
python src/cli.py MSFT --ai

# Historical: what would the system have said on this date?
python src/cli.py MSFT --date 2024-06-01 --forward 60

# Backtest a full date range
python src/cli.py MSFT --backtest --start 2023-01-01 --end 2025-01-01 --forward 60

# With TimesFM ML signal on GPU
python src/cli.py MSFT --ml --ml-device cuda
```

### Example Output

```
────────────────────── VALUE SNIPER - MSFT ───────────────────────
Current Price: $427.34

Support Levels
┌──────────────────────────────┬────────┬─────────┬──────────────────┐
│ Level                        │ Price  │  Drop % │ Allocate         │
├──────────────────────────────┼────────┼─────────┼──────────────────┤
│ Level 1 (Dip Entry)          │$407.59 │  -4.6%  │ 20% of capital   │
│ Level 2 (Deep Value)         │$371.93 │ -13.0%  │ 30% of capital   │
│ Level 3 (Bear Market Entry)  │$360.78 │ -15.6%  │ 50% of capital   │
└──────────────────────────────┴────────┴─────────┴──────────────────┘

Protocol Log
  Macro     TNX 4.49% | Upper Band 4.66% -> NEUTRAL
  Gamma     VIX 16.06 -> NORMAL (multiplier: 1.0)
  Sector    XLK/SPY ratio above SMA20 -> STRONG
  Breadth   SPY/RSP aligned -> HEALTHY
  RSI       59.9 -> STRONG (wait for dip)
  Risk      0/5 -> no discount applied
```

---

## Optional: TimesFM ML Signal (Protocol J)

Adds Google's [TimesFM 2.5](https://github.com/google-research/timesfm) foundation model as a probabilistic 10th signal. The model's 10th and 25th percentile price floors are fed into the clustering as additional support evidence.

**GPU (CUDA), ~500ms per forecast:**
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements-ml.txt
python src/cli.py MSFT --ml --ml-device cuda
```

**CPU, ~15-30s per forecast:**
```bash
pip install -r requirements-ml.txt
python src/cli.py MSFT --ml
```

First run downloads model weights from HuggingFace (~1 GB, one-time). Enable in the dashboard via the **ML Forecast (Protocol J)** toggle in the sidebar.

---

## Optional: AI Strategic Analysis

Add a `GEMINI_API_KEY` to your `.env` file, then:

```bash
python src/cli.py MSFT --ai
```

Generates a 300-500 word "Wall Street analyst" breakdown: market structure warnings, valuation sweet spots, options intelligence, position sizing rationale, and risk scenarios.

---

## Backtesting

```bash
# Default: 7 tickers, 4 start points, targets 5/10/25/50%
python src/benchmark.py

# Bear entry test (the main research scenario)
python src/benchmark.py --tickers AAPL MSFT \
  --starts 2022-01-01 --end 2026-06-01 --targets 10 25 50

# Custom tickers and targets
python src/benchmark.py --tickers MSFT AAPL GOOGL META AMD \
  --starts 2022-01-01 2023-01-01 --end 2026-06-01 --targets 10 25 50
```

Compares Sniper against 14 baselines across two groups: Hold Forever (9 strategies) and Sell+Re-enter (9 strategies per target). Exports `_runtime/benchmark_summary.csv`, `benchmark_trades.csv`, `benchmark_baselines.csv`.

---

## Project Structure

```
value-sniper/
├── src/
│   ├── sniper.py          Core analysis engine, 9 protocols, K-Means clustering
│   ├── dashboard.py       Streamlit web UI
│   ├── cli.py             Full-featured terminal interface
│   ├── backtest.py        Historical point-in-time backtester
│   ├── benchmark.py       Compound strategy benchmark with baselines
│   ├── visualization.py   Chart generation (matplotlib / mplfinance)
│   ├── ml/
│   │   └── timesfm_signal.py   TimesFM Protocol J integration
│   ├── llm/
│   │   ├── base.py             LLM provider interface
│   │   └── gemini.py           Gemini 2.5 Flash implementation
│   └── utils/
│       └── caching.py          TTL-based pickle cache
├── docs/
│   ├── sniper_architecture.md
│   ├── visualization_guide.md
│   └── caching_strategy.md
├── STRATEGY.md            Philosophy: what the system is and how to use it
├── RESEARCH.md            Benchmark methodology, full results, and analysis
├── AGENT.md               Automated install instructions for AI agents
├── requirements.txt       Core dependencies
├── requirements-ml.txt    Optional TimesFM dependencies
└── .env.example           API key template
```

---

## Further Reading

- [STRATEGY.md](STRATEGY.md) - full philosophy: what the system is, how to use it, and what it cannot do
- [RESEARCH.md](RESEARCH.md) - full benchmark: 14 entry strategies, two groups, bear entry analysis, year-by-year returns
- [docs/sniper_architecture.md](docs/sniper_architecture.md) - technical deep-dive on signal pipeline
- [docs/visualization_guide.md](docs/visualization_guide.md) - explanation of every chart

---

## License

MIT - see [LICENSE](LICENSE).
