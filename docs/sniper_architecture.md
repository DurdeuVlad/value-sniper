# Project: The Value Sniper - Quantitative Entry System
**Version:** 2.0.0 (Fundamentally Aware)
**Target:** US Tech Equities (Nasdaq-100)

---

## 1. The "Glass Box" Philosophy
This system is designed to be **Explainable**. It does not just give a number; it proves *why* that number is valid using 9 layers of verification.

## 2. Research Protocols

### The "Green Light" Filters (Is it safe?)
*   **Protocol E (Sector):** `XLK / SPY`. If Tech is lagging, we delete the Aggressive Buy level.
*   **Protocol H (Breadth):** `SPY` vs `RSP`. If the rally is "Narrow" (only Giants rising), we delete the Aggressive Buy level.
*   **Protocol B (Gamma):** `VIX`.
    *   `> 25`: Panic (Discount 5%).
    *   `< 15`: Complacency (Discount 3%).

### The "Discount" Filters (Is it cheap?)
*   **Protocol G (Valuation):** `Price-to-Sales`.
    *   `> 30`: Extreme Risk (-10%).
    *   `> 15`: Elevated Risk (-5%).
*   **Protocol F (Momentum):** `RSI`.
    *   `> 70`: Overbought (-5% on L1).
    *   `> 55`: Strong (-2% on L1).
*   **Protocol I (Trend):** `ADX`.
    *   `> 30`: Falling Knife Risk (-2% on L1).

### The "Targeting" Engines (Where to buy?)
*   **Protocol C (Options):** Max Pain & High OI Walls.
*   **Protocol D (Liquidity):** Unfilled Gaps.
*   **Clustering:** K-Means aggregation of all signals.

---

## 3. Order Generation Logic

### The Defensive Shift
If **Sector Weakness** OR **Narrow Breadth** is detected:
1.  **DELETE Level 1** (Aggressive).
2.  Shift Level 2 -> Level 1.
3.  Shift Level 3 -> Level 2.
4.  Create **Level 3 (Disaster)**: Mean - 3 Standard Deviations.

### The Waterfall Sort
After all discounts are applied, prices are sorted Descending.
*   `Final L1` = Highest Price.
*   `Final L2` = Middle Price.
*   `Final L3` = Lowest Price.
*   *Guarantee:* L1 is never cheaper than L2.

---

## 4. AI Integration Layer
*   **Provider:** Google Gemini 2.5 Flash.
*   **Strategy:** Batched "Mega-Prompt".
    *   Sends all data (Price + 6 Charts) in one request.
    *   Receives structured JSON response.
*   **Retry Logic:** Smart parsing of `Retry-After` headers + Exponential Backoff.
