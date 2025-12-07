# Visualization Roadmap: The Sniper Dashboard

**Version:** 1.0.0
**Status:** Planning

---

## 1. Objective
To transition the "Value Sniper" from a black-box CLI tool into a "Glass Box" visual analytics platform. The goal is to provide the user with an interactive dashboard that visualizes the *confluence* of data (Price, Options, Macro, Gaps) in a single view, allowing for manual verification of the algorithmic signals.

## 2. Current State vs. Future State

| Feature | Current Implementation (v1) | Target Implementation (v2) |
| :--- | :--- | :--- |
| **Interface** | CLI + Static PNG | Interactive Web Dashboard (Localhost) |
| **Charts** | Static Matplotlib Image | Zoomable, Pan-able Candlesticks (Plotly) |
| **Options** | Single "Max Pain" Line | Full 3D Volatility Surface / Open Interest Bar Charts |
| **Macro** | Text Log Entry | Overlay Subplots (Yields vs. Tech Price) |
| **Feedback** | None | User can manually adjust/override levels |

## 3. Technology Stack Selection

### Option A: `Streamlit` (Recommended)
*   **Why:** Pure Python, zero HTML/CSS required. Designed specifically for Data Science dashboards.
*   **Pros:** Extremely fast development. Built-in support for Pandas and Plotly.
*   **Cons:** Less customization than a full web app, but sufficient for this tool.

### Option B: `Dash` (by Plotly)
*   **Why:** Enterprise-standard for analytical apps.
*   **Pros:** Highly customizable callbacks.
*   **Cons:** steeper learning curve than Streamlit.

**Decision:** We will use **Streamlit** for its velocity and simplicity.

## 4. Dashboard Architecture

### 4.1. The "Control Panel" (Sidebar)
*   **Ticker Input:** Text field to change stock (e.g., "TSLA").
*   **Date Range:** Slider to adjust lookback period (e.g., "Last 6 Months").
*   **Protocol Toggles:** Checkboxes to enable/disable specific protocols (e.g., "Ignore Gaps").

### 4.2. Main View: The "Sniper Chart"
*   **Library:** `plotly.graph_objects`
*   **Layers:**
    1.  **Candlesticks:** OHLCV data.
    2.  **Sniper Zones:** Horizontal shaded regions (Green/Yellow/Red) representing the 3 calculated levels.
    3.  **Gap Highlighting:** Semi-transparent boxes drawing attention to unfilled gaps.
    4.  **Moving Averages:** SMA 200, SMA 50.

### 4.3. Sub-Views (Tabs)

**Tab 1: Options Intelligence**
*   **Chart:** "The Smile". A bar chart with Strike Price on X-Axis and Open Interest (Calls vs Puts) on Y-Axis.
*   **Highlight:** A vertical line showing the "Max Pain" calculation.

**Tab 2: Macro Context**
*   **Chart:** Dual-axis chart comparing the Target Stock vs. 10-Year Yields (`^TNX`).
*   **Goal:** Visualize the negative correlation (Yields UP = Tech DOWN).

**Tab 3: The "Math" (Logs)**
*   **View:** A clean, formatted table showing the raw log output (similar to `debug_log.txt`) for audit purposes.

## 5. Implementation Steps

### Phase 1: Streamlit Integration
1.  Add `streamlit` and `plotly` to `requirements.txt`.
2.  Create `src/dashboard.py`.
3.  Migrate `TechSniperAI` logic to be callable as a library function (returning data, not just printing).

### Phase 2: Interactive Components
1.  Implement the Plotly Candlestick chart.
2.  Map the "Sniper Levels" as interactive horizontal lines on the Plotly chart.

### Phase 3: Advanced Visuals
1.  Build the Options Open Interest histogram.
2.  Build the Macro-Correlation chart.

## 6. Execution Command
New usage pattern:
```bash
streamlit run src/dashboard.py
```
This will open a browser window at `http://localhost:8501`.

---
*End of Roadmap*
