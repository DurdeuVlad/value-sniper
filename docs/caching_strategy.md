# Caching Strategy: The Value Sniper

**Version:** 1.0.0
**Status:** Implemented

---

## 1. Objective
Reduce latency and external API call volume to Yahoo Finance and Google Gemini by utilizing a local caching layer. This prevents rate-limiting and speeds up repeated analyses.

## 2. Implemented Strategy: Local File-Based Caching

### 2.1. Storage Mechanism
*   **Location:** `./.cache/` directory in the project root (automatically created and git-ignored).
*   **Format:** `pickle` for Python object serialization (e.g., Pandas DataFrames).

### 2.2. Cache Granularity & Expiration (TTL - Time-To-Live)

| Data Type | Cache Key | TTL | Rationale |
| :--- | :--- | :--- | :--- |
| **Stock OHLCV** | `{TICKER}_OHLCV_5Y` | 15 Minutes | Daily candles are volatile. Fetched for 5 years for robust indicator calculation. |
| **Macro Data** (`^TNX`, `^VIX`) | `MACRO_TNX`, `MACRO_VIX` | 30 Minutes | Macro trends shift slowly intra-day; 30m resolution is sufficient for "Regime" detection. |
| **Sector Data** (`XLK`, `SPY`, `RSP`) | `SECTOR_XLK`, `SECTOR_SPY`, `MARKET_RSP` | 30 Minutes | Sector performance and breadth. |
| **Options Chain** | `{TICKER}_OPTIONS_PAIN` | 60 Minutes | Open Interest (OI) updates are not real-time. "Max Pain" is a structural magnet. |
| **AI Batch Analysis** | `{TICKER}_FULL_ANALYSIS_V2` | 24 Hours (1440 min) | Strategic AI insights change slowly. Reduces API calls significantly. |

### 2.3. How it Works
*   Before any data fetch or AI call, the system checks if a valid (non-expired) cache file exists for that data type.
*   If a cache hit occurs, data is loaded instantly from disk.
*   If a cache miss (or expired data), a fresh API call is made, and the new data is saved to the cache.
*   The `--no-cache` CLI flag bypasses the cache, forcing fresh data.

### 2.4. Rate Limit Handling (Gemini AI)
*   The system implements a **Smart Retry** mechanism for Gemini API calls.
*   If a 429 "Quota Exceeded" error is received, the system parses the `retry_delay` provided by the API (e.g., "retry in 27s").
*   It then waits for the specified duration + a buffer (visually displaying a countdown in the UI) before retrying the API call. This prevents repeated failures and allows the Free Tier quota to reset.