import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
import warnings
import argparse
import sys
import os
import re
from visualization import SniperPlotter
from utils.caching import CacheManager
from llm.gemini import GeminiProvider
from dotenv import load_dotenv

load_dotenv()

# Suppress warnings for cleaner console output
warnings.filterwarnings("ignore")

class TechSniperAI:
    def __init__(self, ticker, use_cache=True, llm_provider=None, lookback_period="1y"):
        self.ticker = ticker.upper()
        self.use_cache = use_cache
        self.cache = CacheManager()
        self.llm_provider = llm_provider
        self.lookback_period = lookback_period
        self.stock = yf.Ticker(self.ticker)
        print(f"--- INITIALIZING SNIPER SYSTEM FOR {self.ticker} (Fetching 5y for Indicators) ---")
        
        # 1. Fetch Data
        try:
            # --- STOCK DATA (TTL: 15 mins) ---
            # Always fetch 5y to ensure SMA200/ADX are valid for the requested view
            cache_key_stock = f"{self.ticker}_OHLCV_5Y"
            self.df = None
            
            if self.use_cache:
                self.df = self.cache.load(cache_key_stock, ttl_minutes=15)
                
            if self.df is None:
                print(f"Fetching historical data (Live, 5y)...")
                self.df = yf.download(self.ticker, period="5y", interval="1d", progress=False)
                if not self.df.empty and self.use_cache:
                    self.cache.save(cache_key_stock, self.df)
            else:
                print("Using Cached Market Data...")

            if self.df.empty:
                print(f"Error: No data found for ticker {self.ticker}")
                self.current_price = 0
                return

            # --- MACRO DATA (TTL: 15 mins) ---
            self.tnx = None
            self.vix = None
            
            if self.use_cache:
                self.tnx = self.cache.load("MACRO_TNX", ttl_minutes=30)
                self.vix = self.cache.load("MACRO_VIX", ttl_minutes=30)
                
            if self.tnx is None:
                print("Fetching macro data ^TNX (Live)...")
                self.tnx = yf.download("^TNX", period="6mo", interval="1d", progress=False)
                if self.use_cache: self.cache.save("MACRO_TNX", self.tnx)
            
            if self.vix is None:
                print("Fetching macro data ^VIX (Live)...")
                self.vix = yf.download("^VIX", period="3mo", interval="1d", progress=False)
                if self.use_cache: self.cache.save("MACRO_VIX", self.vix)

            # --- SECTOR DATA (Protocol E) ---
            self.xlk = None
            self.spy = None
            
            if self.use_cache:
                self.xlk = self.cache.load("SECTOR_XLK", ttl_minutes=30)
                self.spy = self.cache.load("SECTOR_SPY", ttl_minutes=30)
            
            if self.xlk is None:
                print("Fetching sector data XLK (Live)...")
                self.xlk = yf.download("XLK", period="6mo", interval="1d", progress=False)
                if self.use_cache: self.cache.save("SECTOR_XLK", self.xlk)
                
            if self.spy is None:
                print("Fetching sector data SPY (Live)...")
                self.spy = yf.download("SPY", period="6mo", interval="1d", progress=False)
                if self.use_cache: self.cache.save("SECTOR_SPY", self.spy)

            # --- BREADTH DATA (Protocol H) ---
            self.rsp = None
            if self.use_cache:
                self.rsp = self.cache.load("MARKET_RSP", ttl_minutes=30)
            
            if self.rsp is None:
                print("Fetching breadth data RSP (Live)...")
                self.rsp = yf.download("RSP", period="6mo", interval="1d", progress=False)
                if self.use_cache: self.cache.save("MARKET_RSP", self.rsp)
            
            # Cleanup MultiIndex if present (yfinance update compat)
            if isinstance(self.df.columns, pd.MultiIndex): self.df.columns = self.df.columns.get_level_values(0)
            if isinstance(self.tnx.columns, pd.MultiIndex): self.tnx.columns = self.tnx.columns.get_level_values(0)
            if isinstance(self.vix.columns, pd.MultiIndex): self.vix.columns = self.vix.columns.get_level_values(0)
            if isinstance(self.xlk.columns, pd.MultiIndex): self.xlk.columns = self.xlk.columns.get_level_values(0)
            if isinstance(self.spy.columns, pd.MultiIndex): self.spy.columns = self.spy.columns.get_level_values(0)
            if isinstance(self.rsp.columns, pd.MultiIndex): self.rsp.columns = self.rsp.columns.get_level_values(0)

            self.current_price = self.df['Close'].iloc[-1]
            
            # --- FUNDAMENTALS ---
            self.fetch_fundamentals()
            
            self.potential_supports = []
            self.runtime_log = {} # Store step-by-step data
        except Exception as e:
            print(f"Error fetching data: {e}")
            self.current_price = 0

    def fetch_fundamentals(self):
        """Fetches basic valuation metrics (P/E, P/S)."""
        try:
            info = self.stock.info
            self.fundamentals = {
                'PE': info.get('trailingPE', 0),
                'PS': info.get('priceToSalesTrailing12Months', 0),
                'sharesOutstanding': info.get('sharesOutstanding', 0)
            }
        except Exception:
            self.fundamentals = {'PE': 0, 'PS': 0, 'sharesOutstanding': 0}
            
    def _calculate_bollinger_bands(self, series, window=20, num_std=2):
        if series.empty: return pd.Series(), pd.Series()
        rolling_mean = series.rolling(window=window).mean()
        rolling_std = series.rolling(window=window).std()
        return rolling_mean + (rolling_std * num_std), rolling_mean - (rolling_std * num_std)

    def analyze_macro_regime(self):
        """Protocol A: Yield Sensitivity"""
        if self.tnx.empty: 
            self.runtime_log['Macro Protocol'] = "TNX Data Missing"
            return 1.0
        
        tnx_upper, _ = self._calculate_bollinger_bands(self.tnx['Close'])
        current_tnx = self.tnx['Close'].iloc[-1]
        upper_band = tnx_upper.iloc[-1]
        
        log_entry = f"TNX: {current_tnx:.3f}% | Upper Band: {upper_band:.3f}%"
        
        if not tnx_upper.empty and current_tnx > upper_band:
            print(f"[MACRO] Yields at Resistance. Tech bounce probable.")
            self.runtime_log['Macro Protocol'] = f"{log_entry} -> SIGNAL: BULLISH (Yield Reversion)"
            return 1.05 # Boost entry price slightly
        
        self.runtime_log['Macro Protocol'] = f"{log_entry} -> SIGNAL: NEUTRAL"
        return 1.0

    def analyze_gamma_regime(self):
        """Protocol B: Volatility/Gamma"""
        if self.vix.empty: 
            self.runtime_log['Gamma Protocol'] = "VIX Data Missing"
            return 1.0
        
        current_vix = self.vix['Close'].iloc[-1]
        
        if current_vix > 25:
            status = "HIGH FEAR (Negative Gamma)"
            discount = 0.95 # Demand 5% discount
        elif current_vix < 15:
            status = "COMPLACENCY (Contrarian Risk)"
            discount = 0.97 # Demand 3% discount
        else:
            status = "NORMAL"
            discount = 1.0
            
        print(f"[GAMMA] VIX: {current_vix:.2f} -> {status}")
        self.runtime_log['Gamma Protocol'] = f"VIX: {current_vix:.2f} -> {status} (Multiplier: {discount})"
        return discount

    def find_breakaway_gaps(self):
        """Protocol D: Unfilled Gaps"""
        if self.df.empty: return
        self.df['Vol_SMA20'] = self.df['Volume'].rolling(20).mean()
        
        found_gaps = []
        
        for i in range(1, len(self.df) - 5):
            curr, prev = self.df.iloc[i], self.df.iloc[i-1]
            if curr['Low'] > prev['High']: # Gap Up
                if curr['Volume'] > (prev['Vol_SMA20'] * 1.5): # High Vol
                    # Check if unfilled
                    if self.df['Low'].iloc[i+1:].min() > prev['High']:
                        gap_price = prev['High']
                        self.potential_supports.append(gap_price) # Add twice for weight
                        self.potential_supports.append(gap_price)
                        found_gaps.append(f"Date: {self.df.index[i].date()} | Price: ${gap_price:.2f} | Vol Ratio: {curr['Volume']/prev['Vol_SMA20']:.1f}x")

        self.runtime_log['Gap Protocol'] = found_gaps if found_gaps else ["No major breakaway gaps found."]

    def analyze_sector_strength(self):
        """Protocol E: Sector Relative Strength (XLK vs SPY)"""
        if self.xlk.empty or self.spy.empty:
            self.runtime_log['Sector Protocol'] = "Sector Data Missing"
            return True # Assume strong if missing to default to standard behavior

        # Align dates
        common_idx = self.xlk.index.intersection(self.spy.index)
        xlk_close = self.xlk.loc[common_idx]['Close']
        spy_close = self.spy.loc[common_idx]['Close']
        
        ratio = xlk_close / spy_close
        sma20 = ratio.rolling(window=20).mean()
        
        current_ratio = ratio.iloc[-1]
        current_sma = sma20.iloc[-1]
        
        is_strong = current_ratio > current_sma
        
        status = "STRONG (Outperforming)" if is_strong else "WEAK (Underperforming)"
        print(f"[SECTOR] Tech Relative Strength: {status}")
        
        self.runtime_log['Sector Protocol'] = f"XLK/SPY Ratio: {current_ratio:.4f} | SMA20: {current_sma:.4f} -> SIGNAL: {status}"
        self.sector_ratio_series = ratio # Store for visualization
        self.sector_sma_series = sma20
        
        return is_strong

    def _calculate_adx(self, df, period=14):
        """Calculates ADX indicator."""
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        
        tr1 = pd.DataFrame(high - low)
        tr2 = pd.DataFrame(abs(high - close.shift(1)))
        tr3 = pd.DataFrame(abs(low - close.shift(1)))
        frames = [tr1, tr2, tr3]
        tr = pd.concat(frames, axis=1, join='inner').max(axis=1)
        
        atr = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
        minus_di = 100 * (abs(minus_dm).ewm(alpha=1/period, adjust=False).mean() / atr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(alpha=1/period, adjust=False).mean()
        return adx

    def analyze_trend_strength(self):
        """Protocol I: ADX Trend Strength"""
        if self.df.empty: 
            self.runtime_log['Trend Protocol'] = "Data Missing"
            return 0
            
        self.df['ADX'] = self._calculate_adx(self.df)
        current_adx = self.df['ADX'].iloc[-1]
        
        # Determine Trend Direction (SMA50)
        sma50 = self.df['Close'].rolling(50).mean().iloc[-1]
        price = self.df['Close'].iloc[-1]
        trend = "UP" if price > sma50 else "DOWN"
        
        status = "NEUTRAL"
        if current_adx > 25:
            status = f"STRONG {trend} (ADX>25)"
        elif current_adx < 20:
            status = "CHOPPY / RANGE (ADX<20)"
            
        print(f"[TREND] ADX: {current_adx:.2f} -> {status}")
        self.runtime_log['Trend Protocol'] = f"ADX: {current_adx:.2f} | Trend: {trend} -> SIGNAL: {status}"
        return current_adx

    def analyze_market_breadth(self):
        """Protocol H: Market Breadth (SPY vs RSP)"""
        if self.spy.empty or self.rsp.empty:
            self.runtime_log['Breadth Protocol'] = "Data Missing"
            return 0.0, True # Return 0.0 for breadth_delta and True for is_healthy if data is missing

        # Calculate trends (SMA50)
        spy_sma50 = self.spy['Close'].rolling(50).mean().iloc[-1]
        rsp_sma50 = self.rsp['Close'].rolling(50).mean().iloc[-1]
        
        current_spy = self.spy['Close'].iloc[-1]
        current_rsp = self.rsp['Close'].iloc[-1]
        
        spy_uptrend = current_spy > spy_sma50
        rsp_downtrend = current_rsp < rsp_sma50

        # Calculate breadth_delta for explicit check
        spy_chg = (self.spy['Close'].iloc[-1] / self.spy['Close'].iloc[0] - 1) * 100
        rsp_chg = (self.rsp['Close'].iloc[-1] / self.rsp['Close'].iloc[0] - 1) * 100
        breadth_delta = spy_chg - rsp_chg # This is the breadth_gap
        
        if spy_uptrend and rsp_downtrend:
            status = "DIVERGENCE (Narrow Rally - RISK)"
            is_healthy = False
        else:
            status = "HEALTHY (Aligned)" # or aligned bearish, but not 'divergent'
            is_healthy = True
            
        print(f"[BREADTH] Market Structure: {status}")
        self.runtime_log['Breadth Protocol'] = f"SPY Uptrend: {spy_uptrend} | RSP Downtrend: {rsp_downtrend} -> SIGNAL: {status}"
        return breadth_delta, is_healthy

    def calculate_max_pain(self):
        """Protocol C: Max Pain via Option Chain"""
        try:
            # Check Cache first (TTL: 60 mins)
            cache_key = f"{self.ticker}_OPTIONS_PAIN"
            if self.use_cache:
                cached_pain = self.cache.load(cache_key, ttl_minutes=60)
                if cached_pain is not None:
                    # print("Using Cached Options Data...")
                    self.df_pain = cached_pain
                    # Find max pain from cached df
                    max_pain = 0
                    min_loss = float('inf')
                    # We need to re-calc the max pain scalar or store it. 
                    # Simpler to just re-calc quickly from the small DF
                    for idx, row in self.df_pain.iterrows():
                        k = row['Strike']
                        loss = np.sum(np.maximum(0, k - self.df_pain['Strike']) * self.df_pain['Call_OI']) + \
                               np.sum(np.maximum(0, self.df_pain['Strike'] - k) * self.df_pain['Put_OI'])
                        if loss < min_loss: min_loss, max_pain = loss, k
                    
                    print(f"[OPTIONS] Max Pain Strike: ${max_pain} (Cached)")
                    self.potential_supports.append(max_pain)
                    self.runtime_log['Options Protocol'] = f"Max Pain Strike: ${max_pain} (Put/Call Balance)"
                    return

            options = self.stock.options
            if not options: return
            target_date = options[min(len(options)-1, 4)] # Approx Monthly
            chain = self.stock.option_chain(target_date)
            
            # Combine Calls and Puts
            if chain.calls.empty and chain.puts.empty: return

            pain_data = []
            strikes = set(chain.calls.strike).union(set(chain.puts.strike))
            for k in strikes:
                c_oi = chain.calls[chain.calls.strike == k]['openInterest'].sum() if not chain.calls.empty else 0
                p_oi = chain.puts[chain.puts.strike == k]['openInterest'].sum() if not chain.puts.empty else 0
                pain_data.append({'Strike': k, 'Call_OI': c_oi, 'Put_OI': p_oi})
            
            # Calculate Pain
            min_loss, max_pain = float('inf'), 0
            df_pain = pd.DataFrame(pain_data)
            self.df_pain = df_pain # Store for visualization
            
            # Save to Cache
            if self.use_cache:
                self.cache.save(cache_key, df_pain)

            for k in df_pain['Strike']:
                loss = np.sum(np.maximum(0, k - df_pain['Strike']) * df_pain['Call_OI']) + \
                       np.sum(np.maximum(0, df_pain['Strike'] - k) * df_pain['Put_OI'])
                if loss < min_loss: min_loss, max_pain = loss, k
            
            print(f"[OPTIONS] Max Pain Strike: ${max_pain}")
            self.potential_supports.append(max_pain)
            self.runtime_log['Options Protocol'] = f"Max Pain Strike: ${max_pain} (Put/Call Balance)"
        except Exception as e:
            self.runtime_log['Options Protocol'] = f"Failed to calc Max Pain: {e}"
            pass

    def _calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def analyze_momentum_regime(self):
        """Protocol F: RSI Momentum (Rubber Band)"""
        if self.df.empty: return 50.0
        
        self.df['RSI'] = self._calculate_rsi(self.df['Close'])
        current_rsi = self.df['RSI'].iloc[-1]
        
        status = "NEUTRAL"
        if current_rsi < 30: status = "OVERSOLD (Prime Entry)"
        elif current_rsi > 70: status = "OVERBOUGHT (Do Not Chase)"
        elif current_rsi < 45: status = "WEAK (Good for Accumulation)"
        elif current_rsi > 55: status = "STRONG (Wait for Dip)"
        
        print(f"[RSI] Momentum: {current_rsi:.2f} -> {status}")
        self.runtime_log['Momentum Protocol'] = f"RSI-14: {current_rsi:.2f} -> {status}"
        return current_rsi

    def analyze_valuation_regime(self):
        """Protocol G: Valuation Safety (Price-to-Sales)"""
        ps_ratio = self.fundamentals.get('PS', 0)
        
        if ps_ratio > 30:
            multiplier = 0.90
            status = "EXTREME (Demanding 10% Discount)"
        elif ps_ratio > 15:
            multiplier = 0.95
            status = "ELEVATED (Demanding 5% Discount)"
        else:
            multiplier = 1.0
            status = "FAIR"
            
        print(f"[VALUATION] P/S Ratio: {ps_ratio:.2f} -> {status}")
        self.runtime_log['Valuation Protocol'] = f"P/S: {ps_ratio:.2f} -> {status}"
        return multiplier

    def run_full_analysis(self, orders, progress_callback=None):
        """Runs a batched AI analysis for all components (Strategic + Charts)."""
        if not self.llm_provider:
            return {}

        # Check Cache (TTL: 24 Hours)
        cache_key = f"{self.ticker}_FULL_ANALYSIS_V2"
        
        if self.use_cache:
            cached_report = self.cache.load(cache_key, ttl_minutes=1440)
            if cached_report:
                if progress_callback: progress_callback("Loaded cached analysis.")
                return cached_report

        print(f"\n[AI] Batched analysis for {self.ticker}...")
        
        # Inject Fundamentals
        self.runtime_log['Valuation'] = f"P/E: {self.fundamentals.get('PE', 0):.2f} | P/S: {self.fundamentals.get('PS', 0):.2f}"
        
        # Prepare Data Package
        data_package = {
            "ticker": self.ticker,
            "orders": orders,
            "logs": self.runtime_log,
            "options_context": self.runtime_log.get('Options Protocol', 'N/A'),
            "macro_context": self.runtime_log.get('Macro Protocol', 'N/A'),
            "vix_context": self.runtime_log.get('Gamma Protocol', 'N/A'),
            "breadth_context": self.runtime_log.get('Breadth Protocol', 'N/A'),
            "trend_context": self.runtime_log.get('Trend Protocol', 'N/A'),
            "rsi_context": self.runtime_log.get('Momentum Protocol', 'N/A'),
            "clustering_context": f"Final Orders: {orders}. Sector: {self.runtime_log.get('Sector Protocol', 'N/A')}"
        }
        
        # Call API (Single Request)
        report = self.llm_provider.generate_full_report(data_package, progress_callback)
        
        # Save to Cache
        if self.use_cache and "Error" not in report.get('strategic_analysis', ''):
            self.cache.save(cache_key, report)
            
        return report

    def _calculate_valuation_ratios_at_price(self, target_price):
        """Calculates estimated P/E and P/S at a given target price."""
        current_pe = self.fundamentals.get('PE', 0)
        current_ps = self.fundamentals.get('PS', 0)
        
        estimated_pe = 0
        estimated_ps = 0

        if self.current_price > 0: # Ensure current_price is not zero to avoid division by zero
            if current_pe > 0:
                estimated_pe = current_pe * (target_price / self.current_price)

            if current_ps > 0:
                estimated_ps = current_ps * (target_price / self.current_price)
            
        return estimated_pe, estimated_ps

    def generate_orders(self):
        if self.current_price == 0:
            return {}

        # 1. Gather Intelligence
        macro_mod = self.analyze_macro_regime()
        gamma_mod = self.analyze_gamma_regime()
        val_mod = self.analyze_valuation_regime()
        is_tech_strong = self.analyze_sector_strength()
        breadth_gap, is_market_healthy = self.analyze_market_breadth() # Get breadth_gap
        current_rsi = self.analyze_momentum_regime()
        current_adx = self.analyze_trend_strength()
        self.find_breakaway_gaps()
        self.calculate_max_pain()
        
        # Add SMA200 and Lower BB
        if len(self.df) > 200:
            self.potential_supports.append(self.df['Close'].rolling(200).mean().iloc[-1])
        
        _, lower_bb = self._calculate_bollinger_bands(self.df['Close'])
        if not lower_bb.empty:
            self.potential_supports.append(lower_bb.iloc[-1])

        # 2. Filter & Cluster
        valid_supports = [x for x in self.potential_supports if x < self.current_price and not np.isnan(x)]
        
        # Fallback safety
        while len(valid_supports) < 3: 
            valid_supports.append(self.current_price * 0.95)
            valid_supports.append(self.current_price * 0.90)
            valid_supports.append(self.current_price * 0.85)

        kmeans = KMeans(n_clusters=3, n_init=10, random_state=42)
        kmeans.fit(np.array(valid_supports).reshape(-1, 1))
        centers = sorted(kmeans.cluster_centers_.flatten(), reverse=True)

        # Calculate Level 4 (3-Sigma Crash) early for use in STANDARD MODE
        rolling_std = self.df['Close'].rolling(20).std().iloc[-1]
        level_4 = self.df['Close'].rolling(20).mean().iloc[-1] - (rolling_std * 3)

        # 3. Apply Sector Logic (Dynamic Aggression) 
        
        # Protocol F: RSI Discounting
        rsi_mod = 1.0
        if current_rsi > 70: rsi_mod = 0.95
        elif current_rsi > 55: rsi_mod = 0.98
        
        # Protocol I: ADX Trend Safety
        adx_mod = 1.0
        if current_adx > 30: # Strong Trend
             adx_mod = 0.98 # Widen margins slightly for strong momentum
        
        orders_with_labels_and_values = []
        risk_alert_message = "" # Initialize risk alert

        if is_tech_strong and is_market_healthy:
            # STANDARD MODE
            l1_label = "Level 1 (Aggressive)"
            if current_rsi > 55:
                l1_label = f"Level 1 (Aggressive - RSI Adjusted {rsi_mod:.2f}x)"
            
            # Check for Visual Invalidation due to Narrow Rally
            if breadth_gap > 5.0:
                l1_label = f"~~{l1_label}~~ (INVALID - Narrow Rally)"
                risk_alert_message = "⚠️ RISK ALERT: Level 1 is invalidated due to weak market breadth. Focus buying power on Level 2 and Level 3."
            
            orders_with_labels_and_values.append(
                (centers[0] * macro_mod * gamma_mod * rsi_mod * adx_mod, l1_label))
            orders_with_labels_and_values.append(
                (centers[1] * macro_mod * gamma_mod, "Level 2 (Deep Value)"))
            orders_with_labels_and_values.append(
                (level_4, "Level 3 (Capitulation)"))
            
        else:
            # DEFENSIVE SHIFT
            reason = "Sector Weakness" if not is_tech_strong else "Market Breadth Divergence"
            print(f"[RISK] {reason} Detected. shifting orders down (Deleting Level 1).")
            self.runtime_log['Sector Logic'] = f"{reason} Detected -> SHIFTING ORDERS DOWN (Deleting Aggressive Level)"
            
            # Level 1 is effectively deleted/shifted, so no need for strikethrough in this branch
            orders_with_labels_and_values.append(
                (centers[1] * macro_mod * gamma_mod, "Level 1 (Value - Shifted)"))
            orders_with_labels_and_values.append(
                (centers[2] * macro_mod * gamma_mod, "Level 2 (Capitulation - Shifted)"))
            orders_with_labels_and_values.append(
                (level_4, "Level 3 (Disaster/3-Sigma)"))


        # WATERFALL SORT (Safety Mechanism)
        # Sort by value in descending order to ensure L1 > L2 > L3
        orders_with_labels_and_values.sort(key=lambda x: x[0], reverse=True)
        
        final_orders = {}
        
        # Define qualitative possibility for each level's rank
        possibility_rank = {
            0: "Normal Probability (Expected Pullback)", # Corresponds to the highest level
            1: "Medium Probability (Significant Correction)", # Corresponds to the middle level
            2: "Low Probability (Extreme Capitulation)" # Corresponds to the lowest level
        }

        # Re-initialize the keys based on whether it's Standard or Defensive
        # This logic determines the FINAL labels based on the sorted positions
        if is_tech_strong and is_market_healthy:
            final_labels_in_order = ["Level 1 (Aggressive)", "Level 2 (Deep Value)", "Level 3 (Capitulation)"]
            # Apply strikethrough to the Level 1 label if it was invalidated
            if "~~Level 1 (Aggressive)~~" in orders_with_labels_and_values[0][1]: # Check if original L1 label was marked for strikethrough
                 final_labels_in_order[0] = orders_with_labels_and_values[0][1] # Use the strikethrough label

        else: # Defensive Shift
            final_labels_in_order = ["Level 1 (Value - Shifted)", "Level 2 (Capitulation - Shifted)", "Level 3 (Disaster/3-Sigma)"]

        for i in range(3):
            price_at_level = orders_with_labels_and_values[i][0] # Get sorted price
            label_for_level = final_labels_in_order[i] # Use the fixed labels for the sorted positions
            
            percent_drop = 0
            if self.current_price > 0:
                percent_drop = ((self.current_price - price_at_level) / self.current_price) * 100

            pe, ps = self._calculate_valuation_ratios_at_price(price_at_level)
            final_orders[label_for_level] = {
                'price': price_at_level,
                'estimated_pe': pe,
                'estimated_ps': ps,
                'percent_drop': percent_drop,
                'possibility': possibility_rank[i], # Assign possibility based on rank
                'is_invalidated_l1': (risk_alert_message != "" and i==0) # Flag for dashboard to apply strikethrough on price
            }
        
        # Add risk alert to runtime log if applicable
        if risk_alert_message:
            self.runtime_log['Recommendation'] = risk_alert_message
        else:
            self.runtime_log['Recommendation'] = "Focus buying power on Level 1, Level 2 and Level 3." # Default recommendation
                
        return final_orders

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Value Sniper - Quantitative Entry System')
    parser.add_argument('ticker', type=str, nargs='?', default='MSFT', help='Stock Ticker Symbol (default: MSFT)')
    parser.add_argument('--plot', action='store_true', help='Generate chart visualization and logs in _runtime/')
    parser.add_argument('--no-cache', action='store_true', help='Force live data fetching (ignore cache)')
    parser.add_argument('--ai', action='store_true', help='Enable AI Analysis via Gemini (Requires GEMINI_API_KEY)')
    args = parser.parse_args()

    TARGET = args.ticker
    
    # Initialize AI Provider
    ai_provider = None
    if args.ai:
        try:
            ai_provider = GeminiProvider()
        except ValueError as e:
            print(f"\n[ERROR] Cannot enable AI: {e}")
            print("Please set the GEMINI_API_KEY environment variable.")
            sys.exit(1)
    
    bot = TechSniperAI(TARGET, use_cache=not args.no_cache, llm_provider=ai_provider)
    orders = bot.generate_orders()
    
    if orders:
        print(f"\n>>> SNIPER ORDERS FOR {TARGET} (Current: ${bot.current_price:.2f}) <<<")
        for k, v in orders.items():
            price_str = f"${v['price']:.2f}"
            if v.get('is_invalidated_l1'):
                price_str = f"~~{price_str}~~"
            
            print(f"{k}: {price_str} (-{v['percent_drop']:.2f}%) (Est. P/E: {v['estimated_pe']:.2f}, Est. P/S: {v['estimated_ps']:.2f}) (Possibility: {v['possibility']})")
        
        if 'Recommendation' in bot.runtime_log:
            print(f"\n{bot.runtime_log['Recommendation']}")

        if args.plot:
            plotter = SniperPlotter(bot)
            # Add final orders to log
            bot.runtime_log['FINAL ORDERS'] = orders
            plotter.log_steps(bot.runtime_log)
            # The plotter expects just prices, so we'll pass those.
            plotter_orders = {k: v['price'] for k, v in orders.items()}
            plotter.plot_sniper_view(plotter_orders)
            
        if args.ai:
            def cli_callback(msg):
                print(f"\r[AI WAIT] {msg:<50}", end="", flush=True)
            
            report = bot.run_full_analysis(orders, progress_callback=cli_callback)
            print("\n" + "="*50)
            print(f"   🤖 GEMINI STRATEGIC ANALYSIS: {TARGET}")
            print("="*50)
            clean_md = lambda t: re.sub(r'\[*\*|__', '', str(t)) # Corrected regex for markdown bold
            print(clean_md(report.get('strategic_analysis', 'Analysis Failed')))
            print("="*50 + "\n")
            
    else:
        print("Could not generate orders due to data errors.")
