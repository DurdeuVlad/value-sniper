# GEMINI Context: Stock Support Calculator (The Value Sniper)

## Project Overview
**Name:** The Value Sniper - Quantitative Entry System (V2.0)
**Purpose:** An "Institutional Grade" decision support system for US Tech Equities. It calculates high-probability entry levels by synthesizing **Macro, Fundamental, and Technical** data.
**Philosophy:** "Glass Box" AI. Every decision must be transparent, visually verifiable, and mathematically sound. No black boxes.

## Core Logic (The Protocols)

The system aggregates 9 distinct signals to generate 3 dynamic orders:

1.  **Protocol A (Macro):** 10Y Yields (`^TNX`) vs Bollinger Bands. (Rate Reversion).
2.  **Protocol B (Gamma):** VIX Fear Gauge. (Discount for Fear OR Complacency).
3.  **Protocol C (Structure):** Options Max Pain & Open Interest Walls.
4.  **Protocol D (Liquidity):** Unfilled Breakaway Gaps (High Volume).
5.  **Protocol E (Sector):** Tech (`XLK`) vs S&P (`SPY`) Relative Strength.
    *   *Action:* If Weak, triggers **Defensive Shift** (Deletes Aggressive Level).
6.  **Protocol F (Momentum):** RSI-14.
    *   *Action:* If >55, applies discounts to Level 1.
7.  **Protocol G (Valuation):** Price-to-Sales (`P/S`).
    *   *Action:* If >15 (Elevated) or >30 (Extreme), applies global discounts (5-10%).
8.  **Protocol H (Breadth):** `SPY` (Cap-Weight) vs `RSP` (Equal-Weight).
    *   *Action:* If Divergent (Narrow Rally), triggers **Defensive Shift**.
9.  **Protocol I (Trend):** ADX Trend Strength.
    *   *Action:* If >30 (Strong Trend), widens margins to catch "falling knives".

## Architecture

### Key Components
*   **`src/sniper.py`:** The Brain. Handles data fetching, protocol logic, and the "Waterfall Sort" (ensuring L1 > L2 > L3).
*   **`src/dashboard.py`:** The Face. A Streamlit Web UI with interactive Plotly charts and dynamic AI explanations.
*   **`src/llm/gemini.py`:** The Analyst. Interfaces with Google Gemini 2.5 to provide qualitative insights via a Batched "Mega-Prompt" (optimizes Rate Limits).

### UX Features
*   **Data Center:** A metrics row (VIX, RSI, ADX, P/S) with color-coded risk signals (Red/Green/Yellow).
*   **Smart Caching:** 24h TTL for AI, 15m for Price.
*   **Resilience:** Auto-retries on AI Rate Limits with visual countdown.

## Setup & Usage

### Installation
```bash
pip install -r requirements.txt
```
*   Create `.env` with `GEMINI_API_KEY`.

### Execution
**The Dashboard (Recommended):**
```bash
streamlit run src/dashboard.py
```
*   Provides full interactivity, visual charts, and AI commentary.

**The CLI (Headless):**
```bash
python src/sniper.py MSFT --ai
```

## Development Conventions
1.  **Safety First:** If data is ambiguous, assume risk. (e.g., Defensive Shift).
2.  **Explainability:** Every chart has a "What is this?" block. Every AI insight is plain text.
3.  **Robustness:** Handle API failures gracefully (Fallbacks, Retries).