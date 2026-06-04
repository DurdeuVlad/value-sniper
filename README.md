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
  <a href="RESULTS.md">Results</a> ·
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
git clone https://github.com/DurdeuVlad/stock-support-calculator
cd stock-support-calculator
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

Full methodology and data in [RESULTS.md](RESULTS.md).

### Across all market conditions tested

| Scenario | Period | Sniper Result | Buy & Hold |
|---|---|---|---|
| Bull market | 2023-2026 | +11% to +47.6% (83% win rate) | +139.7% |
| Bear market | 2022 only | -37.1% (mostly cash, refused most entries) | **-42.4%** |
| Recovery | mid-2022 to 2024 | +15.5% to +52.8% (**100% win rate**) | +111.2% |
| **Blood in the streets** | **2022 crash, hold to 2026** | **AAPL: +107-119% vs +79% B&H** | +204% avg* |

*\* Buy & Hold average dominated by NVDA's +609% AI-structural outlier. See below.*

**The number that matters most:** every trade the Sniper entered and exited (profit target hit) closed at a gain. 100% closed-trade win rate across bull and recovery markets.

### The NVDA caveat — and why it matters

The extended bear-to-recovery test reveals something important. For **AAPL and MSFT**, the Sniper waited through the crash, entered at genuine structural support, and outperformed buy-and-hold by 30–40 percentage points when held to 2026. That is the thesis working exactly as intended.

For **NVDA**, buy-and-hold returned +609% and no entry system comes close. NVDA underwent a fundamental business transformation — gaming chip maker to AI compute monopoly. That is a macro structural call, not a technical entry opportunity. The Sniper is not designed to beat NVDA. It is designed to give you a better entry into AAPL.

**The honest use case:** use the Sniper for concentrated entries into quality Nasdaq-100 names at genuine structural support. Keep your AI/structural macro positions as pure buy-and-hold — they operate on different logic entirely. See [RESULTS.md](RESULTS.md) for the full per-ticker breakdown.

---

## Disclaimer

> **This software is for educational and research purposes only. It does not constitute financial advice, investment advice, or a recommendation to buy or sell any security. All backtested results are historical and do not guarantee future performance. You are solely responsible for your own investment decisions. Trading stocks involves significant risk of loss.**

---

## Installation

**Requirements:** Python 3.10+

```bash
git clone https://github.com/DurdeuVlad/stock-support-calculator
cd stock-support-calculator
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
# Strategy benchmark, compound cycle across multiple start points
python src/benchmark.py --tickers MSFT AAPL NVDA \
  --starts 2023-01-01 2023-07-01 2024-01-01 \
  --end 2026-06-01 --targets 5 10 15 20

# Bear market test
python src/benchmark.py --tickers MSFT AAPL NVDA META \
  --starts 2022-01-03 --end 2023-01-01 --targets 5 10 15 20
```

Exports `_runtime/benchmark_summary.csv`, `benchmark_trades.csv`, `benchmark_baselines.csv`. Includes four baselines: Buy & Hold, DCA, SPY DCA, Random Entry, and Pullback -5%.

---

## Project Structure

```
stock-support-calculator/
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
├── RESULTS.md             Benchmark methodology and full results
├── AGENT.md               Automated install instructions for AI agents
├── requirements.txt       Core dependencies
├── requirements-ml.txt    Optional TimesFM dependencies
└── .env.example           API key template
```

---

## Further Reading

- [STRATEGY.md](STRATEGY.md) - full philosophy: what the system is, how to use it, and what it cannot do
- [RESULTS.md](RESULTS.md) - complete benchmark methodology and results across bull, bear, and recovery markets
- [docs/sniper_architecture.md](docs/sniper_architecture.md) - technical deep-dive on signal pipeline
- [docs/visualization_guide.md](docs/visualization_guide.md) - explanation of every chart

---

## License

MIT - see [LICENSE](LICENSE).
