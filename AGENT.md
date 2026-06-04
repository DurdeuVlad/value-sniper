# AGENT.md — Automated Installation Instructions

This file is intended for AI agents (Claude, Copilot, Cursor, etc.) to automatically install, configure, and verify this project.

---

## Project Overview

**Value Sniper** is a quantitative stock entry system for Nasdaq-100 tech equities. It runs as a Streamlit web dashboard and CLI tool. It uses Python 3.10+, yfinance for market data, scikit-learn for K-Means clustering, and optionally Gemini AI and Google TimesFM for enhanced analysis.

---

## Step 1 — Prerequisites Check

Before installing, verify:

```bash
python --version        # Must be 3.10 or higher
pip --version           # Must be available
git --version           # Must be available
```

If Python < 3.10, stop and ask the user to upgrade.

---

## Step 2 — Clone and Install

```bash
git clone https://github.com/DurdeuVlad/value-sniper
cd value-sniper
pip install -r requirements.txt
```

Expected output: all packages install without errors. Key packages: `yfinance`, `pandas`, `numpy`, `scikit-learn`, `streamlit`, `plotly`, `rich`, `google-generativeai`, `python-dotenv`.

---

## Step 3 — Environment Setup (Optional)

Only required if the user wants AI analysis via Gemini.

```bash
# Linux / macOS / Git Bash
cp .env.example .env

# Windows Command Prompt
copy .env.example .env
```

Then open `.env` and set:
```
GEMINI_API_KEY=your_actual_key_here
```

Get a free key at: https://aistudio.google.com/apikey

If the user does not want AI features, skip this step entirely. The tool works without it.

---

## Step 4 — Verify Installation

Run a smoke test to confirm everything works:

```bash
cd src
python -c "from sniper import TechSniperAI; from backtest import Backtester; from benchmark import simulate_strategy; print('OK')"
```

Expected output: `OK`

If this fails, check:
1. Are you running from the project root or `src/` directory?
2. Is Python 3.10+?
3. Did `pip install -r requirements.txt` complete without errors?

---

## Step 5 — Run a Quick Analysis

```bash
python src/cli.py MSFT
```

Expected output: 3 support levels for MSFT with protocol log. Takes 10-30 seconds on first run (fetches live data), then uses cache.

---

## Step 6 — Launch the Dashboard

```bash
streamlit run src/dashboard.py
```

Opens at `http://localhost:8501`. Select a ticker from the sidebar dropdown and click **Run Analysis**.

---

## Optional: TimesFM ML Signal

Only needed for Protocol J (10th ML signal). Requires ~1GB disk for model weights.

**GPU install (NVIDIA CUDA, fast ~500ms):**
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements-ml.txt
```

**CPU install (slow ~15-30s per analysis):**
```bash
pip install -r requirements-ml.txt
```

Verify TimesFM works:
```bash
python -c "from ml.timesfm_signal import is_available; print('TimesFM available:', is_available())"
```

Run with ML signal:
```bash
python src/cli.py MSFT --ml --ml-device cuda   # GPU
python src/cli.py MSFT --ml                    # CPU
```

---

## Entry Points Summary

| Command | Purpose |
|---|---|
| `streamlit run src/dashboard.py` | Web UI dashboard |
| `python src/cli.py MSFT` | Live CLI analysis |
| `python src/cli.py MSFT --ai` | With Gemini AI summary |
| `python src/cli.py MSFT --ml` | With TimesFM ML signal |
| `python src/cli.py MSFT --date 2024-06-01 --forward 60` | Historical point analysis |
| `python src/cli.py MSFT --backtest --start 2023-01-01 --end 2025-01-01` | Backtest date range |
| `python src/benchmark.py --help` | Full strategy benchmark |

---

## Common Issues and Fixes

**`ModuleNotFoundError: No module named 'rich'`**
```bash
pip install rich
```

**`ModuleNotFoundError: No module named 'sniper'`**
Make sure you run entry points from the project root, not from inside `src/`:
```bash
# Correct
python src/cli.py MSFT

# Wrong
cd src && python cli.py MSFT
```

**`Error: No data found for ticker X`**
The ticker may not exist or yfinance may be rate-limited. Try again in 30 seconds or use a major ticker like MSFT, AAPL, NVDA.

**Streamlit shows spinner indefinitely**
First run fetches ~5 years of market data. Wait 30-60 seconds. Subsequent runs use cache and load in under 5 seconds.

**`GEMINI_API_KEY not found`**
You used `--ai` without setting up `.env`. Either skip `--ai` or follow Step 3 above.

**TimesFM install fails with `Python version` error**
The PyPI version of timesfm requires Python < 3.12. Install from GitHub source instead (already specified in `requirements-ml.txt`).

---

## Project File Map

```
value-sniper/
├── src/
│   ├── sniper.py          Core engine — protocols A through J, K-Means clustering
│   ├── dashboard.py       Streamlit web UI
│   ├── cli.py             Terminal interface (mirrors dashboard functionality)
│   ├── backtest.py        Point-in-time historical backtester
│   ├── benchmark.py       Compound strategy benchmark with 4 baselines
│   ├── visualization.py   Chart generation
│   ├── ml/
│   │   └── timesfm_signal.py   Optional TimesFM ML signal
│   ├── llm/
│   │   ├── base.py             Abstract LLM provider
│   │   └── gemini.py           Gemini 2.5 Flash
│   └── utils/
│       └── caching.py          TTL file cache (auto-created at .cache/)
├── _runtime/              Auto-created: charts, logs, CSV exports
├── .cache/                Auto-created: TTL pickle cache (gitignored)
├── .env.example           Copy to .env and add GEMINI_API_KEY
├── requirements.txt       Core dependencies
├── requirements-ml.txt    Optional TimesFM dependencies
├── STRATEGY.md            System philosophy and usage guide
├── RESEARCH.md            Benchmark methodology, full results, and analysis
└── README.md              Full project documentation
```

---

## What the System Outputs

Three support levels per analysis:

```
Level 1 (Dip Entry)         — Most likely support, ~5-15% below current price
Level 2 (Deep Value)        — Correction support, ~15-25% below
Level 3 (Bear Market Entry) — Capitulation floor, ~25-40% below
```

Each level includes: entry price, % drop from current, estimated P/E and P/S at that price, recommended position sizing (20% / 30% / 50% of intended allocation), and a zone description.

The protocol log shows which of the 9 signals fired and why, making every level fully explainable.
