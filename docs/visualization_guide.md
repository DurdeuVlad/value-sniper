# Visualization Guide: The Sniper Dashboard

**Version:** 2.0.0

The Dashboard (`streamlit run src/dashboard.py`) is the primary interface. It organizes data into layers of evidence.

---

## 1. The Data Center (Top Row)
A "Cockpit View" of the risk metrics. Colors indicate status:
*   **Green:** Favorable / Opportunity.
*   **Red:** Risk / Expensive (Discounts applied).
*   **Grey:** Neutral.

**Metrics:**
*   **VIX:** Fear Gauge. High is scary but cheap; Low is calm but expensive.
*   **RSI:** Momentum. Low (<30) is a buy signal.
*   **ADX:** Trend. High (>30) means "Don't catch the knife."
*   **Breadth:** `SPY - RSP`. High positive means only Giants are rallying (Fragile).

---

## 2. The Charts (Tabs)

### Options Intelligence
*   **Visual:** Bar chart of Open Interest.
*   **Key Insight:** Look for the "Walls" (Tallest Bars). These act as magnets and barriers.

### Macro Regime
*   **Visual:** 10-Year Yields (`^TNX`) vs Bollinger Bands.
*   **Key Insight:** Yields hitting the Red Line (Upper Band) usually trigger a Tech Rally.

### Market Fear (VIX)
*   **Visual:** VIX History.
*   **Key Insight:** Are we in the "Panic Zone" (>25) or "Complacency Zone" (<15)? Both carry risks.

### Market Breadth
*   **Visual:** Green Line (`SPY`) vs Orange Line (`RSP`).
*   **Key Insight:** Divergence. If Green goes up and Orange goes down, the market is weak under the surface.

### Trend Strength (ADX)
*   **Visual:** ADX Line vs Threshold (25).
*   **Key Insight:** If line is high, the trend is powerful. Wait for it to cool off.

### AI Logic
*   **Visual:** Blue Dots (Raw Signals) vs Red Stars (Final Orders).
*   **Key Insight:** Transparency. See exactly how the AI grouped the messy data into clean levels.