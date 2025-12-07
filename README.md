# The Value Sniper - Quantitative Entry System

A quantitative tool for identifying high-probability entry levels for US Tech Equities (specifically Nasdaq-100). This system uses market microstructure research (Options Max Pain, Gamma Regimes, Macro Yields, and Unfilled Gaps) rather than standard technical analysis.

## Features

- **Macro-Yield Sensitivity**: Adjusts entry confidence based on 10-Year Treasury Yield extremes.
- **Gamma Regimes**: Detects negative gamma environments (VIX > 25) to demand deeper safety margins.
- **Max Pain Analysis**: Calculates the options strike price with maximum open interest pain.
- **Gap Analysis**: Identifies unfilled institutional breakaway gaps.
- **Clustering**: Uses K-Means clustering to find confluence zones among these diverse signals.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd stock-support-calculator
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

Run the script from the command line, optionally providing a stock ticker (defaults to MSFT).

**Basic usage:**
```bash
python src/sniper.py
```

**Specify a ticker:**
```bash
python src/sniper.py NVDA
python src/sniper.py AAPL
```

## Visualization ("Glass Box" Mode)

To see the *why* behind the numbers, use the `--plot` flag:

```bash
python src/sniper.py MSFT --plot
```

This will generate 4 chart images in the `_runtime/` folder:
1.  **Main Analysis:** The price chart with your buy levels drawn.
2.  **Options Structure:** The "Max Pain" evidence.
3.  **Macro Regime:** The Treasury Yield analysis.
4.  **AI Logic:** A visual explanation of how the clustering algorithm grouped the signals.

*See [docs/visualization_guide.md](docs/visualization_guide.md) for a detailed explanation of each chart.*

## Interactive Dashboard (Web UI)

For a fully interactive experience (Zoom, Pan, Explore), launch the local web dashboard:

```bash
streamlit run src/dashboard.py
```
This will open the tool in your browser (usually at `http://localhost:8501`).

## AI Strategic Analysis (Powered by Gemini)

To get a qualitative "Wall Street Analyst" summary of the data:

1.  Create a `.env` file in the project root:
    ```
    GEMINI_API_KEY=your_api_key_here
    ```
2.  Run with the `--ai` flag:
    ```bash
    python src/sniper.py MSFT --ai
    ```

## Output Explained

The tool outputs 3 potential entry levels:

*   **Level 1 (Aggressive):** Institutional Floor. Suitable for initial scaling in during standard pullbacks.
*   **Level 2 (Deep Value):** Gap Defense. A strong support level often aligned with unfilled gaps or major moving averages.
*   **Level 3 (Capitulation):** Max Pain / Crash level. Extreme support reserved for high-volatility events.

## Disclaimer

This software is for educational and research purposes only. It does not constitute financial advice. Trading stocks and options involves significant risk.
