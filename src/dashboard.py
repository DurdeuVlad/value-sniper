import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import os
import re
from dotenv import load_dotenv
from sniper import TechSniperAI
from llm.gemini import GeminiProvider

load_dotenv()

# Page Config
st.set_page_config(
    page_title="Value Sniper Dashboard",
    page_icon="🎯",
    layout="wide"
)

# Sidebar
st.sidebar.title("🎯 Value Sniper")

# Big Tech Quick Select
BIG_TECH_STOCKS = {
    "Microsoft (MSFT)": "MSFT",
    "Apple (AAPL)": "AAPL",
    "NVIDIA (NVDA)": "NVDA",
    "Alphabet/Google (GOOGL)": "GOOGL",
    "Amazon (AMZN)": "AMZN",
    "Meta/Facebook (META)": "META",
    "Tesla (TSLA)": "TSLA",
    "Netflix (NFLX)": "NFLX",
    "AMD (AMD)": "AMD",
    "Intel (INTC)": "INTC",
    "Salesforce (CRM)": "CRM",
    "Oracle (ORCL)": "ORCL",
    "Adobe (ADBE)": "ADBE",
    "Cisco (CSCO)": "CSCO",
    "Custom...": None
}

# Dropdown for quick select
quick_select = st.sidebar.selectbox(
    "Quick Select (Big Tech)",
    options=list(BIG_TECH_STOCKS.keys()),
    index=0  # Default to MSFT
)

# Get ticker from dropdown or allow custom input
if BIG_TECH_STOCKS[quick_select] is None:
    ticker = st.sidebar.text_input("Custom Ticker Symbol", value="MSFT").upper()
else:
    ticker = BIG_TECH_STOCKS[quick_select]
    st.sidebar.text(f"Ticker: {ticker}")

timeframe = st.sidebar.selectbox("Lookback Period", ["6mo", "1y", "2y", "5y", "max"], index=1)
use_cache = st.sidebar.checkbox("Use Cache", value=True)
enable_ai = st.sidebar.checkbox("Enable AI Analysis", value=False)

# TimesFM ML Signal (Protocol J)
from ml.timesfm_signal import is_available as timesfm_available, TimesFMSignal
_timesfm_installed = timesfm_available()
st.sidebar.markdown("---")
st.sidebar.markdown("**ML Forecast (Protocol J)**")
if _timesfm_installed:
    import torch
    _has_cuda = torch.cuda.is_available()
    enable_ml = st.sidebar.checkbox("Enable TimesFM Signal", value=False)
    ml_device = st.sidebar.selectbox("Device", options=["cuda", "cpu"] if _has_cuda else ["cpu"], index=0, disabled=not enable_ml)
    if enable_ml:
        _status = f"GPU active ({torch.cuda.get_device_name(0)})" if ml_device == "cuda" else "CPU mode (slow)"
        st.sidebar.caption(f"TimesFM: {_status}")
else:
    enable_ml = False
    ml_device = "cpu"
    st.sidebar.caption("Not installed. Run: `pip install -r requirements-ml.txt`")
st.sidebar.markdown("---")

run_btn = st.sidebar.button("Run Analysis")

# Auto-run if cache is available and no explicit run requested yet
if 'last_ticker' not in st.session_state:
    st.session_state.last_ticker = None
    st.session_state.auto_ran = False

# Check if ticker changed
ticker_changed = st.session_state.last_ticker != ticker
if ticker_changed:
    st.session_state.last_ticker = ticker
    st.session_state.auto_ran = False

# Auto-run logic: run if cache available and ticker just changed
auto_run = False
if use_cache and ticker_changed and not st.session_state.auto_ran:
    # Check if cache exists for this ticker
    from utils.caching import CacheManager
    cache = CacheManager()
    cache_key = f"{ticker}_OHLCV_5Y"
    cached_data = cache.load(cache_key, ttl_minutes=15)
    if cached_data is not None:
        auto_run = True
        st.session_state.auto_ran = True

# Export functionality helper
def generate_markdown_report(ticker, current_price, orders, bot, ai_report=None):
    """Generate a comprehensive markdown report of the analysis."""
    from datetime import datetime
    
    report = f"""# 🎯 Value Sniper Analysis Report
## {ticker}
**Generated:** {datetime.now().strftime("%B %d, %Y at %I:%M %p")}  
**Current Price:** ${current_price:.2f}

---

## 📊 Executive Summary

"""
    
    # Add recommendation first
    if 'Recommendation' in bot.runtime_log:
        report += f"""{bot.runtime_log['Recommendation']}

"""
    
    # Add no-trade warning if present
    if 'No-Trade Warning' in bot.runtime_log:
        report += f"""### ⚠️ WARNING
{bot.runtime_log['No-Trade Warning']}

"""
    
    report += """---

## 💰 Support Levels & Entry Strategy

"""
    
    # Add orders with detailed breakdown
    for label, data in sorted(orders.items(), key=lambda x: x[1]['price'], reverse=True):
        report += f"""### {label}

| Metric | Value |
|--------|-------|
| **Entry Price** | ${data['price']:.2f} |
| **Drop from Current** | -{data['percent_drop']:.2f}% |
| **Position Sizing** | {data.get('position_size', 'N/A')} |
| **Risk Zone** | {data['possibility']} |
| **Est. P/E at Entry** | {data['estimated_pe']:.2f} |
| **Est. P/S at Entry** | {data['estimated_ps']:.2f} |

**Rationale:** {data['possibility']}. This level represents a strategic accumulation zone based on technical and fundamental confluence.

"""
    
    report += """---

## 📈 Fundamental Analysis

### Valuation Metrics

| Metric | Current Value | Assessment |
|--------|---------------|------------|
| **P/E Ratio** | {:.2f} | {} |
| **P/S Ratio** | {:.2f} | {} |

""".format(
        bot.fundamentals.get('PE', 0),
        "Expensive" if bot.fundamentals.get('PE', 0) > 50 else ("Reasonable" if bot.fundamentals.get('PE', 0) < 25 else "Neutral"),
        bot.fundamentals.get('PS', 0),
        "Extreme valuation" if bot.fundamentals.get('PS', 0) > 30 else ("Elevated" if bot.fundamentals.get('PS', 0) > 15 else "Fair value")
    )
    
    report += """---

## 🎯 Technical Indicators

"""
    
    # Add technical indicators with context
    indicators_added = False
    
    if not bot.vix.empty:
        cur_vix = bot.vix['Close'].iloc[-1]
        vix_status = "High Fear (Negative Gamma)" if cur_vix > 25 else ("Complacency Risk" if cur_vix < 15 else "Normal")
        report += f"""### VIX (Fear Gauge)
- **Current:** {cur_vix:.2f}
- **Status:** {vix_status}
- **Interpretation:** {'Market in fear mode - potential buying opportunity' if cur_vix > 25 else ('Low volatility - watch for complacency' if cur_vix < 15 else 'Normal market conditions')}

"""
        indicators_added = True
    
    if 'RSI' in bot.df.columns:
        cur_rsi = bot.df['RSI'].iloc[-1]
        rsi_status = "Oversold" if cur_rsi < 30 else ("Overbought" if cur_rsi > 70 else ("Weak" if cur_rsi < 45 else ("Strong" if cur_rsi > 55 else "Neutral")))
        report += f"""### RSI (Momentum)
- **Current:** {cur_rsi:.2f}
- **Status:** {rsi_status}
- **Interpretation:** {'Prime entry zone - momentum exhausted to downside' if cur_rsi < 30 else ('Avoid chasing - overbought conditions' if cur_rsi > 70 else ('Good for accumulation' if cur_rsi < 45 else 'Wait for dip'))}

"""
        indicators_added = True
    
    if 'ADX' in bot.df.columns:
        cur_adx = bot.df['ADX'].iloc[-1]
        adx_status = "Strong Trend" if cur_adx > 25 else "Choppy/Range"
        report += f"""### ADX (Trend Strength)
- **Current:** {cur_adx:.2f}
- **Status:** {adx_status}
- **Interpretation:** {'Strong directional movement - respect the trend' if cur_adx > 25 else 'Weak trend - good environment for range-bound strategies'}

"""
        indicators_added = True
    
    # Add breadth analysis
    if not bot.spy.empty and not bot.rsp.empty:
        spy_chg = (bot.spy['Close'].iloc[-1] / bot.spy['Close'].iloc[0] - 1) * 100
        rsp_chg = (bot.rsp['Close'].iloc[-1] / bot.rsp['Close'].iloc[0] - 1) * 100
        breadth_delta = spy_chg - rsp_chg
        
        breadth_status = "Narrow Rally (Warning)" if breadth_delta > 5 else ("Broad Rally (Healthy)" if breadth_delta < -5 else "Aligned")
        report += f"""### Market Breadth (SPY vs RSP)
- **SPY Change:** {spy_chg:.2f}%
- **RSP Change:** {rsp_chg:.2f}%
- **Breadth Gap:** {breadth_delta:.2f}%
- **Status:** {breadth_status}
- **Interpretation:** {'Only large caps rising - fragile rally structure' if breadth_delta > 5 else ('Broad market participation - healthy rally' if breadth_delta < -5 else 'Normal market conditions')}

"""
        indicators_added = True
    
    if not indicators_added:
        report += "*Technical indicators unavailable*\n\n"
    
    report += """---

## 🔬 Detailed Protocol Analysis

"""
    
    # Add protocol results with better formatting
    protocol_order = ['Risk Score', 'Sector Protocol', 'Breadth Protocol', 'Momentum Protocol', 'Trend Protocol', 
                     'Gamma Protocol', 'Valuation Protocol', 'Macro Protocol', 'Gap Protocol', 'Options Protocol']
    
    for protocol in protocol_order:
        if protocol in bot.runtime_log:
            result = bot.runtime_log[protocol]
            report += f"""### {protocol}
"""
            if isinstance(result, list):
                for item in result:
                    report += f"- {item}\n"
                report += "\n"
            else:
                report += f"{result}\n\n"
    
    # Add any remaining protocols not in the order
    for protocol, result in bot.runtime_log.items():
        if protocol not in protocol_order and protocol not in ['FINAL ORDERS', 'Valuation', 'Recommendation', 'No-Trade Warning', 'Sector Logic']:
            report += f"""### {protocol}
"""
            if isinstance(result, list):
                for item in result:
                    report += f"- {item}\n"
                report += "\n"
            else:
                report += f"{result}\n\n"
    
    report += """---

## 🤖 AI Strategic Analysis

"""
    
    # Add comprehensive AI analysis if available
    if ai_report:
        # Strategic Analysis
        if 'strategic_analysis' in ai_report:
            report += """### Overall Strategic Assessment

"""
            raw_analysis = ai_report.get('strategic_analysis', '')
            if isinstance(raw_analysis, dict):
                for k, v in raw_analysis.items():
                    report += f"**{k}:** {v}\n\n"
            else:
                report += f"{raw_analysis}\n\n"
        
        # Individual insights
        insights = [
            ('options_insight', 'Options Intelligence'),
            ('macro_insight', 'Macro Regime'),
            ('vix_insight', 'Volatility Analysis'),
            ('breadth_insight', 'Market Breadth'),
            ('trend_insight', 'Trend Strength'),
            ('rsi_insight', 'Momentum Analysis'),
            ('clustering_insight', 'Support Level Reliability')
        ]
        
        report += """### Detailed Component Analysis

"""
        
        for key, title in insights:
            if key in ai_report and ai_report[key] and ai_report[key] != "Unavailable":
                report += f"""#### {title}
{ai_report[key]}

"""
    else:
        report += "*AI analysis not available. Run analysis with 'Enable AI Analysis' checkbox to get strategic insights.*\n\n"
    
    report += """---

## 📖 How to Use This Report

### Position Sizing Strategy
The recommended position sizing follows a pyramid approach:
- **Level 1:** 20% of allocated capital (most aggressive entry)
- **Level 2:** 30% of allocated capital (deep value zone)
- **Level 3:** 50% of allocated capital (maximum safety margin)

This ensures your average cost improves with deeper discounts while maintaining flexibility.

### Risk Management
1. **Never deploy all capital at once** - Scale in as price reaches each level
2. **Use stop losses** - Consider setting stops 5-8% below Level 3 if market structure deteriorates
3. **Monitor protocols** - If defensive shift triggers or no-trade warnings appear, reduce position sizes
4. **Valuation matters** - Higher P/E and P/S at entry = higher risk. Adjust accordingly.

### Market Regime Considerations
- **Bull Market:** Focus on Levels 1-2 for entries
- **Volatile/Uncertain Market:** Be patient, wait for Level 2-3
- **Bear Market:** Level 3 only, or wait on sidelines if no-trade warning present

---

## 📝 Important Disclaimers

### Risk Disclosure
This analysis is for **educational and research purposes only**. It does NOT constitute:
- Financial advice
- Investment recommendations
- Trading signals
- Professional guidance

### Limitations
- Past performance does not guarantee future results
- Technical analysis is probabilistic, not deterministic
- Market conditions can change rapidly
- Black swan events can invalidate all support levels
- Options data reflects current positioning, which changes daily

### Responsibility
You are solely responsible for your trading decisions. The Value Sniper system is a **decision support tool**, not an automated trading system. Always:
- Do your own research
- Understand your risk tolerance
- Consider your investment timeline
- Consult with financial professionals if needed

---

## 📊 System Information

**Analysis Engine:** Value Sniper v2.0  
**Protocols Active:** 9 (Macro, Gamma, Options, Gaps, Sector, Momentum, Valuation, Trend, Breadth)  
**Clustering Method:** K-Means (3 clusters)  
**AI Provider:** {}

---

*Report generated by Value Sniper - Quantitative Entry System*  
*For questions or feedback: github.com/DurdeuVlad/stock-support-calculator*
""".format("Google Gemini 2.5 Flash" if ai_report else "Not enabled")
    
    return report

# Main Content
st.title(f"Sniper Analysis: {ticker}")

if run_btn or auto_run:
    if auto_run:
        st.info("📦 Using cached data - running analysis automatically...")
    
    with st.spinner(f"Analyzing {ticker}..."):
        # Setup AI
        ai_provider = None
        if enable_ai:
            try:
                ai_provider = GeminiProvider()
            except ValueError:
                st.sidebar.error("GEMINI_API_KEY not found in .env")
        
        # ML signal
        ml_signal_instance = None
        if enable_ml and _timesfm_installed:
            ml_signal_instance = TimesFMSignal(device=ml_device)

        # Run the Bot
        bot = TechSniperAI(ticker, use_cache=use_cache, llm_provider=ai_provider, lookback_period=timeframe)
        orders = bot.generate_orders(ml_signal=ml_signal_instance)
        
        if not orders:
            st.error("Failed to generate orders. Check ticker or data source.")
        else:
            # --- AI ANALYSIS SECTION (BATCHED) ---
            ai_report = {}
            if enable_ai:
                status_box = st.empty()
                def dashboard_callback(msg):
                    status_box.warning(f"🤖 {msg}")
                
                ai_report = bot.run_full_analysis(orders, progress_callback=dashboard_callback)
                status_box.empty()
                
                raw_analysis = ai_report.get('strategic_analysis', '')
                if isinstance(raw_analysis, dict):
                    formatted_analysis = ""
                    for k, v in raw_analysis.items():
                        formatted_analysis += f"**{k}:** {v}\n\n"
                    clean_analysis = formatted_analysis
                else:
                    # Clean up escape sequences and normalize formatting
                    clean_text = str(raw_analysis)
                    # Replace escaped newlines with actual newlines
                    clean_text = clean_text.replace('\\n', '\n')
                    # Remove any markdown formatting the AI might add despite instructions
                    clean_text = clean_text.replace('**', '').replace('__', '')
                    clean_analysis = clean_text
                
                # Display AI analysis in expandable container for better readability
                with st.expander("🤖 AI Strategic Analysis", expanded=True):
                    st.text(clean_analysis)  # Use st.text for plain text formatting

            # --- EXPORT FUNCTIONALITY ---
            st.markdown("---")
            
            # Generate report once and store in session state to prevent reset
            report_key = f'markdown_report_{ticker}_{bot.current_price}'
            if report_key not in st.session_state:
                st.session_state[report_key] = generate_markdown_report(ticker, bot.current_price, orders, bot, ai_report if enable_ai else None)
            
            export_col1, export_col2 = st.columns([3, 1])
            
            with export_col1:
                st.caption("📄 Export complete analysis as markdown file for record-keeping and sharing")
            
            with export_col2:
                st.download_button(
                    label="📥 Export Report",
                    data=st.session_state[report_key],
                    file_name=f"{ticker}_sniper_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                    width="stretch",
                    key=f"download_btn_{ticker}_{bot.current_price}"
                )

            # --- 1. KEY LEVELS (Top Metrics) ---
            st.subheader("Key Sniper Levels")
            
            # Display Current Price first
            st.metric("Current Price", f"${bot.current_price:.2f}")

            # Display No-Trade Warning if present
            if 'No-Trade Warning' in bot.runtime_log:
                st.error(f"**{bot.runtime_log['No-Trade Warning']}**")

            # Display Recommendation if available
            if 'Recommendation' in bot.runtime_log:
                st.info(f"**Recommendation:** {bot.runtime_log['Recommendation']}")

            # Dynamic columns based on active levels (handles Defensive Shifts/Renaming)
            sorted_orders = sorted(orders.items(), key=lambda x: x[1]['price'], reverse=True)
            cols = st.columns(len(sorted_orders))
            
            for i, (label, price_dict) in enumerate(sorted_orders):
                # Determine delta_color based on estimated P/E and P/S
                delta_color_for_valuation = "off"
                # Check for estimated P/E risk
                if price_dict['estimated_pe'] > 50: # High PE
                    delta_color_for_valuation = "inverse"
                elif price_dict['estimated_pe'] > 25 and delta_color_for_valuation != "inverse": # Elevated PE, if not already inverse
                    delta_color_for_valuation = "inverse"

                # Check for estimated P/S risk (using thresholds from fcol2 for overall PS Logic)
                if price_dict['estimated_ps'] > 30: # Extreme P/S
                    delta_color_for_valuation = "inverse"
                elif price_dict['estimated_ps'] > 15 and delta_color_for_valuation != "inverse": # Elevated P/S, if not already inverse
                    delta_color_for_valuation = "inverse"

                if delta_color_for_valuation == "off" and price_dict['estimated_pe'] > 0 and price_dict['estimated_ps'] > 0:
                     delta_color_for_valuation = "normal" # If not inverse, assume normal/good valuation at this level

                # Display price
                display_price = f"${price_dict['price']:.2f}"

                cols[i].metric(
                    label,
                    display_price,
                    delta=f"-{price_dict['percent_drop']:.2f}% | {price_dict.get('position_size', 'N/A')}",
                    delta_color=delta_color_for_valuation,
                    help=f"{price_dict['possibility']} | P/E: {price_dict['estimated_pe']:.2f}, P/S: {price_dict['estimated_ps']:.2f}"
                )
            
            st.markdown("---")
            fcol1, fcol2 = st.columns(2)
            
            # P/E Logic
            pe = bot.fundamentals.get('PE', 0)
            pe_lbl = "Neutral"
            pe_col = "off"
            if pe > 50: pe_lbl, pe_col = "Expensive", "inverse"
            elif pe > 0 and pe < 25: pe_lbl, pe_col = "Reasonable", "normal"
            fcol1.metric("P/E Ratio", f"{pe:.2f}", delta=pe_lbl, delta_color=pe_col, help="Price-to-Earnings. How many years of earnings it takes to pay back the price. >50 is Growth/Hype. <20 is Value.")
            
            # P/S Logic
            ps = bot.fundamentals.get('PS', 0)
            ps_lbl = "Neutral"
            ps_col = "off"
            if ps > 30: ps_lbl, ps_col = "Extreme (10% Disc)", "inverse"
            elif ps > 15: ps_lbl, ps_col = "Elevated (5% Disc)", "inverse"
            elif ps > 0 and ps < 10: ps_lbl, ps_col = "Fair Value", "normal"
            fcol2.metric("P/S Ratio", f"{ps:.2f}", delta=ps_lbl, delta_color=ps_col, help="Price-to-Sales. How much you pay for $1 of revenue. >15: Priced for perfection (High Risk). <5: Value territory.")
            
            # --- TECHNICAL DATA CENTER ---
            st.markdown("---")
            t1, t2, t3, t4 = st.columns(4)
            
            # Helper
            def get_last(series): return series.iloc[-1] if not series.empty else 0
            
            # VIX (Fear)
            cur_vix = bot.vix['Close'].iloc[-1] if not bot.vix.empty else 0
            vix_delta = "Neutral"
            vix_color = "off"
            if cur_vix > 25: 
                vix_delta = "High Fear (Risk)"
                vix_color = "inverse" # Red
            elif cur_vix < 15:
                vix_delta = "Complacency (Risk)"
                vix_color = "inverse" # Red
            else:
                vix_delta = "Safe Zone"
                vix_color = "normal" # Green
            t1.metric("VIX (Fear)", f"{cur_vix:.2f}", delta=vix_delta, delta_color=vix_color, help="The 'Fear Gauge'. Measures expected volatility. High (>25): Panic selling (Cheap). Low (<15): Complacency (Expensive/Top).")
            
            # RSI (Momentum)
            cur_rsi = get_last(bot.df['RSI']) if 'RSI' in bot.df.columns else 50
            rsi_delta = "Neutral"
            rsi_color = "off"
            if cur_rsi > 70:
                rsi_delta = "Overbought (Risk)"
                rsi_color = "inverse" # Red
            elif cur_rsi < 30:
                rsi_delta = "Oversold (Buy)"
                rsi_color = "normal" # Green
            t2.metric("RSI (Momentum)", f"{cur_rsi:.2f}", delta=rsi_delta, delta_color=rsi_color, help="Relative Strength Index. Measures speed of price moves. >70: Overbought (Price stretched too high). <30: Oversold (Price stretched too low).")
            
            # ADX (Trend)
            cur_adx = get_last(bot.df['ADX']) if 'ADX' in bot.df.columns else 0
            adx_delta = "Neutral"
            adx_color = "off"
            if cur_adx > 30:
                adx_delta = "Strong Trend (Knife Risk)"
                adx_color = "inverse" # Red
            elif cur_adx < 20:
                adx_delta = "Range (Safe)"
                adx_color = "normal" # Green
            t3.metric("ADX (Trend)", f"{cur_adx:.2f}", delta=adx_delta, delta_color=adx_color, help="Average Directional Index. Measures Trend STRENGTH, not direction. >25: Strong Trend. If price is falling & ADX is high -> Falling Knife (Wait).")
            
            # Breadth (Gap)
            if not bot.spy.empty and not bot.rsp.empty:
                spy_chg = (bot.spy['Close'].iloc[-1] / bot.spy['Close'].iloc[0] - 1) * 100
                rsp_chg = (bot.rsp['Close'].iloc[-1] / bot.rsp['Close'].iloc[0] - 1) * 100
                breadth_delta = spy_chg - rsp_chg
                
                b_label = "Aligned"
                b_color = "off"
                if breadth_delta > 5:
                    b_label = "Narrow Rally (Risk)"
                    b_color = "inverse" # Red
                elif breadth_delta < -5:
                    b_label = "Broad Rally (Safe)"
                    b_color = "normal" # Green
                    
                t4.metric("Breadth Gap", f"{breadth_delta:.2f}%", delta=b_label, delta_color=b_color, help="Difference between Tech Giants (SPY) and Average Stocks (RSP). Positive: Narrow Rally (Fragile). Negative: Broad Participation (Healthy).")
            else:
                t4.metric("Breadth Gap", "N/A")
            
            # --- PERFORMANCE METRICS ---
            st.markdown("---")
            p1, p2, p3, p4 = st.columns(4)
            
            # Calc Metrics on Full Data
            year_high = bot.df['High'].rolling(252).max().iloc[-1]
            year_low = bot.df['Low'].rolling(252).min().iloc[-1]
            curr = bot.current_price
            
            d_high = (curr / year_high - 1) * 100
            d_low = (curr / year_low - 1) * 100
            
            # Approx ATR (High - Low) smoothed
            tr = bot.df['High'] - bot.df['Low']
            atr = tr.rolling(14).mean().iloc[-1]
            atr_pct = (atr / curr) * 100
            
            # Rel Vol
            vol_sma = bot.df['Volume'].rolling(20).mean().iloc[-1]
            rel_vol = bot.df['Volume'].iloc[-1] / vol_sma
            
            p1.metric("Dist 52W High", f"{d_high:.2f}%", delta="Resistance" if d_high > -5 else "Room to Run", delta_color="off")
            p2.metric("Dist 52W Low", f"+{d_low:.2f}%", delta="Support" if d_low < 5 else "Trend Up", delta_color="normal")
            p3.metric("Volatility (ATR)", f"{atr_pct:.2f}%", delta="High" if atr_pct > 3 else "Normal", delta_color="inverse")
            p4.metric("Relative Vol", f"{rel_vol:.2f}x", delta="High Activity" if rel_vol > 1.5 else "Quiet", delta_color="normal")

            # --- 2. MAIN CHART (Interactive) ---
            st.subheader("Price Discovery & Sniper Zones")
            
            # Slice for Display
            cutoff = bot.df.index[0]
            if timeframe == '6mo': cutoff = pd.Timestamp.now() - pd.DateOffset(months=6)
            elif timeframe == '1y': cutoff = pd.Timestamp.now() - pd.DateOffset(years=1)
            elif timeframe == '2y': cutoff = pd.Timestamp.now() - pd.DateOffset(years=2)
            elif timeframe == '5y': cutoff = pd.Timestamp.now() - pd.DateOffset(years=5)
            
            # Ensure cutoff is tz-aware if index is (likely yes from yfinance)
            if bot.df.index.tz is not None:
                cutoff = cutoff.tz_localize(bot.df.index.tz)
            
            df_display = bot.df[bot.df.index >= cutoff]
            
            fig = go.Figure(data=[go.Candlestick(x=df_display.index,
                            open=df_display['Open'],
                            high=df_display['High'],
                            low=df_display['Low'],
                            close=df_display['Close'],
                            name=ticker)])

            # Add Support Lines
            for label, price_dict in orders.items():
                color = 'blue' # Default
                if 'Level 1' in label: color = 'orange'
                elif 'Level 2' in label: color = 'green'
                elif 'Level 3' in label: color = 'red'
                elif 'Disaster' in label: color = 'darkred'
                
                fig.add_hline(y=price_dict['price'], line_dash="dash", line_color=color, annotation_text=label, annotation_position="bottom right")

            # Add SMA 200 (Calculated on full data, sliced for display)
            if len(bot.df) > 200:
                # Calculate full SMA first
                full_sma = bot.df['Close'].rolling(200).mean()
                # Slice it
                sma_display = full_sma[full_sma.index >= cutoff]
                
                fig.add_trace(go.Scatter(x=sma_display.index, y=sma_display, mode='lines', name='SMA 200', line=dict(color='purple', width=1)))

            fig.update_layout(height=600, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("CHART LEGEND: Orange = Aggressive (L1), Green = Deep Value (L2), Red = Capitulation/Crash (L3). Dotted lines represent the AI's calculated buy zones.")
            
            # --- 3. EVIDENCE TABS ---
            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab_bt = st.tabs(["Options Intelligence", "Macro Regime", "Market Fear", "Market Breadth", "Trend Strength", "Momentum (RSI)", "AI Logic", "Backtest"])
            
            with tab1:
                st.subheader("Options Open Interest ('The Smile')")
                if hasattr(bot, 'df_pain') and not bot.df_pain.empty:
                    pain_df = bot.df_pain
                    # Filter range
                    center_price = bot.current_price
                    pain_df = pain_df[(pain_df['Strike'] > center_price * 0.7) & (pain_df['Strike'] < center_price * 1.3)]
                    
                    fig_opt = go.Figure()
                    fig_opt.add_trace(go.Bar(x=pain_df['Strike'], y=pain_df['Call_OI'], name='Calls', marker_color='green'))
                    fig_opt.add_trace(go.Bar(x=pain_df['Strike'], y=pain_df['Put_OI'], name='Puts', marker_color='red'))
                    
                    fig_opt.update_layout(barmode='stack', title=f"Max Pain Analysis", template="plotly_dark")
                    st.plotly_chart(fig_opt, use_container_width=True)
                    
                    if enable_ai:
                        ai_insight = ai_report.get('options_insight', 'Unavailable')
                        if ai_insight and ai_insight != "Unavailable":
                            st.success(f"🤖 **AI Insight:** {ai_insight}")

                    st.info("**WHAT IS THIS?** A map of the 'Casino's Liability'.\n- **Green Bars (Calls):** Betting UP. Tall Green = Resistance (Ceiling).\n- **Red Bars (Puts):** Betting DOWN. Tall Red = Support (Floor/Safety Net).")
                else:
                    st.warning("No Options Data Available")

            with tab2:
                st.subheader("Macro Yield Sensitivity (^TNX)")
                if not bot.tnx.empty:
                    macro_df = bot.tnx.iloc[-120:].copy()
                    window = 20
                    macro_df['SMA'] = macro_df['Close'].rolling(window=window).mean()
                    macro_df['STD'] = macro_df['Close'].rolling(window=window).std()
                    macro_df['Upper'] = macro_df['SMA'] + (macro_df['STD'] * 2)
                    
                    fig_macro = go.Figure()
                    fig_macro.add_trace(go.Scatter(x=macro_df.index, y=macro_df['Close'], name='10Y Yield', line=dict(color='white')))
                    fig_macro.add_trace(go.Scatter(x=macro_df.index, y=macro_df['Upper'], name='Upper Band', line=dict(color='red', dash='dash')))
                    
                    fig_macro.update_layout(title="Bond Yields vs. Panic Threshold", template="plotly_dark")
                    st.plotly_chart(fig_macro, use_container_width=True)
                    
                    if enable_ai:
                        ai_insight = ai_report.get('macro_insight', 'Unavailable')
                        if ai_insight and ai_insight != "Unavailable":
                            st.success(f"🤖 **AI Insight:** {ai_insight}")

                    st.info("**WHAT IS THIS?** A gauge of Interest Rate Stress. Tech stocks move OPPOSITE to rates. When Rates (White Line) hit the Red Line, it means bonds are oversold. SIGNAL: If White Line > Red Line --> BUY TECH (Expect a rate reversion).")
                else:
                    st.warning("No Macro Data Available")

            with tab3:
                st.subheader("Market Sentiment (^VIX)")
                if not bot.vix.empty:
                    vix_df = bot.vix.iloc[-120:].copy()
                    
                    fig_vix = go.Figure()
                    fig_vix.add_trace(go.Scatter(x=vix_df.index, y=vix_df['Close'], name='VIX', line=dict(color='orange')))
                    fig_vix.add_hline(y=25, line_dash="dash", line_color="red", annotation_text="High Fear (>25)", annotation_position="top left")
                    fig_vix.add_hline(y=15, line_dash="dash", line_color="green", annotation_text="Complacency (<15)", annotation_position="bottom left")
                    
                    fig_vix.update_layout(title="VIX Fear Gauge", template="plotly_dark")
                    st.plotly_chart(fig_vix, use_container_width=True)
                    
                    if enable_ai:
                        ai_insight = ai_report.get('vix_insight', 'Unavailable')
                        if ai_insight and ai_insight != "Unavailable":
                            st.success(f"🤖 **AI Insight:** {ai_insight}")
                            
                    st.info("**WHAT IS THIS?** The 'Fear Gauge'. Measures expected volatility.\n- **> 25 (High Fear):** Negative Gamma. Market Makers sell into drops (Crash Accelerator).\n- **< 15 (Complacency):** Calm market.")
                else:
                    st.warning("No VIX Data Available")

            with tab4:
                st.subheader("Market Breadth (SPY vs RSP)")
                if not bot.spy.empty and not bot.rsp.empty:
                    # Normalize
                    spy_norm = (bot.spy['Close'] / bot.spy['Close'].iloc[0] - 1) * 100
                    rsp_norm = (bot.rsp['Close'] / bot.rsp['Close'].iloc[0] - 1) * 100
                    
                    fig_breadth = go.Figure()
                    fig_breadth.add_trace(go.Scatter(x=spy_norm.index, y=spy_norm, name='SPY (Cap Weighted)', line=dict(color='green')))
                    fig_breadth.add_trace(go.Scatter(x=rsp_norm.index, y=rsp_norm, name='RSP (Equal Weighted)', line=dict(color='orange')))
                    
                    fig_breadth.update_layout(title="Market Breadth Divergence (%)", template="plotly_dark")
                    st.plotly_chart(fig_breadth, use_container_width=True)
                    
                    if enable_ai:
                        ai_insight = ai_report.get('breadth_insight', 'Unavailable')
                        if ai_insight and ai_insight != "Unavailable":
                            st.success(f"🤖 **AI Insight:** {ai_insight}")
                    
                    st.info("**WHAT IS THIS?** Comparing the 'Generals' (SPY) vs. the 'Soldiers' (RSP).\n- **Alignment:** Both rising = Healthy Rally.\n- **Divergence:** SPY rising but RSP falling = Narrow Rally (WARNING).")
                else:
                    st.warning("No Breadth Data Available")

            with tab5:
                st.subheader("Trend Strength (ADX)")
                if 'ADX' in bot.df.columns:
                    fig_adx = go.Figure()
                    fig_adx.add_trace(go.Scatter(x=bot.df.index, y=bot.df['ADX'], name='ADX', line=dict(color='cyan')))
                    fig_adx.add_hline(y=25, line_dash="dash", line_color="yellow", annotation_text="Strong Trend (>25)")
                    
                    fig_adx.update_layout(title="ADX Trend Strength", template="plotly_dark")
                    st.plotly_chart(fig_adx, use_container_width=True)
                    
                    if enable_ai:
                        ai_insight = ai_report.get('trend_insight', 'Unavailable')
                        if ai_insight and ai_insight != "Unavailable":
                            st.success(f"🤖 **AI Insight:** {ai_insight}")
                            
                    st.info("**WHAT IS THIS?** ADX measures Trend Strength (not direction).\n- **> 25:** Strong Trend (Don't fight it).\n- **< 20:** Choppy/Range (Buy dips safely).")
                else:
                    st.warning("No ADX Data Available")

            with tab6:
                st.subheader("Momentum (RSI)")
                if 'RSI' in bot.df.columns:
                    fig_rsi = go.Figure()
                    fig_rsi.add_trace(go.Scatter(x=bot.df.index, y=bot.df['RSI'], name='RSI', line=dict(color='purple')))
                    fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought (>70)")
                    fig_rsi.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold (<30)")
                    
                    fig_rsi.update_layout(title="RSI Momentum", template="plotly_dark")
                    st.plotly_chart(fig_rsi, use_container_width=True)
                    
                    if enable_ai:
                        ai_insight = ai_report.get('rsi_insight', 'Unavailable')
                        if ai_insight and ai_insight != "Unavailable":
                            st.success(f"🤖 **AI Insight:** {ai_insight}")
                            
                    st.info("**WHAT IS THIS?** Relative Strength Index (Momentum).\n- **> 70 (Overbought):** Price may correct down.\n- **< 30 (Oversold):** Price may bounce up.")
                else:
                    st.warning("No RSI Data Available")

            with tab7:
                st.subheader("AI Clustering Logic")
                # Need to extract only price values from the orders for plotting
                # The orders dict now contains dicts, so we need to get the price
                raw_signals_prices = [x for x in bot.potential_supports if x < bot.current_price and not np.isnan(x)]
                final_orders_prices = [v['price'] for v in orders.values()]
                
                # Jitter for display
                jitter = np.random.uniform(-0.1, 0.1, size=len(raw_signals_prices))
                
                fig_ai = go.Figure()
                fig_ai.add_trace(go.Scatter(x=raw_signals_prices, y=jitter, mode='markers', name='Raw Signals', marker=dict(color='blue', size=10)))
                fig_ai.add_trace(go.Scatter(x=final_orders_prices, y=[0]*len(final_orders_prices), mode='markers', name='Final Orders', marker=dict(symbol='star', color='red', size=20)))
                
                fig_ai.update_yaxes(visible=False)
                fig_ai.update_layout(title="K-Means Clustering Visualization", template="plotly_dark", height=300)
                st.plotly_chart(fig_ai, use_container_width=True)
                
                if enable_ai:
                    ai_insight = ai_report.get('clustering_insight', 'Unavailable')
                    if ai_insight and ai_insight != "Unavailable":
                        st.success(f"🤖 **AI Insight:** {ai_insight}")

                tfm_log = bot.runtime_log.get('Protocol J - TimesFM', '')
                if tfm_log and 'Skipped' not in tfm_log:
                    st.success(f"📡 **Protocol J (TimesFM ML):** {tfm_log}")
                elif tfm_log:
                    st.caption(f"Protocol J: {tfm_log}")
                st.info("**WHAT IS THIS?** The 'Brain' of the algorithm. BLUE DOTS = Every potential support found (Gaps, Moving Averages, Option Strikes). RED STARS = The consensus. The AI groups the Blue Dots and finds the center. Note: Blue dots are jittered vertically to show overlaps.")

            with tab_bt:
                st.subheader("Backtest — Historical Level Accuracy")
                st.caption("Runs the sniper at monthly historical dates and checks if predicted levels were hit (intraday Low) within the forward window.")
                import sys as _sys
                _bt_src = os.path.join(os.path.dirname(__file__))
                if _bt_src not in _sys.path:
                    _sys.path.insert(0, _bt_src)
                from backtest import Backtester, generate_monthly_dates
                bt_col1, bt_col2, bt_col3 = st.columns(3)
                with bt_col1:
                    bt_start = st.date_input("Start Date", value=pd.Timestamp.now() - pd.DateOffset(years=1))
                with bt_col2:
                    bt_end = st.date_input("End Date", value=pd.Timestamp.now() - pd.DateOffset(days=1))
                with bt_col3:
                    bt_forward = st.select_slider("Forward Window (days)", options=[30, 60, 90, 120], value=60)
                run_bt = st.button("Run Backtest", key="run_backtest")
                if run_bt:
                    import plotly.graph_objects as _go_bt
                    bt_dates = generate_monthly_dates(str(bt_start), str(bt_end))
                    if not bt_dates:
                        st.warning("No valid dates in selected range.")
                    else:
                        st.info(f"Running {len(bt_dates)} dates for {ticker}...")
                        bt_runner = Backtester(ticker, forward_days=bt_forward, verbose=False)
                        with st.spinner(f"Backtesting {ticker}..."):
                            bt_results = bt_runner.run(bt_dates)
                        if not bt_results:
                            st.error("No results returned.")
                        else:
                            summary = bt_runner.summarize(bt_results)
                            import re as _re
                            def _pct(s):
                                m = _re.search(r'(\d+)%', str(s))
                                return int(m.group(1)) if m else 0
                            m1, m2, m3, m4 = st.columns(4)
                            m1.metric("L1 Hit Rate", summary['l1_hit_rate'])
                            m2.metric("L2 Hit Rate", summary['l2_hit_rate'])
                            m3.metric("L3 Hit Rate", summary['l3_hit_rate'])
                            m4.metric("Avg Max Drawdown", summary['avg_max_drawdown'])
                            fig_bt_bar = _go_bt.Figure(data=[_go_bt.Bar(
                                x=['Level 1 (Dip)', 'Level 2 (Deep Value)', 'Level 3 (Bear Market)'],
                                y=[_pct(summary['l1_hit_rate']), _pct(summary['l2_hit_rate']), _pct(summary['l3_hit_rate'])],
                                marker_color=['#26a69a', '#ffa726', '#ef5350'],
                                text=[summary['l1_hit_rate'], summary['l2_hit_rate'], summary['l3_hit_rate']],
                                textposition='outside',
                            )])
                            fig_bt_bar.update_layout(title="Level Hit Rates (%)", yaxis=dict(range=[0, 110], title="%"), template="plotly_dark", height=300)
                            st.plotly_chart(fig_bt_bar, use_container_width=True)
                            rows = []
                            for r in bt_results:
                                rows.append({'Date': r.analysis_date, 'Price': f"${r.price_at_analysis:.2f}", 'L1': f"${r.level_1_price:.2f} (-{r.l1_pct_drop:.1f}%)", 'L2': f"${r.level_2_price:.2f} (-{r.l2_pct_drop:.1f}%)", 'L3': f"${r.level_3_price:.2f} (-{r.l3_pct_drop:.1f}%)", 'L1 Hit': "HIT" if r.l1_hit else "miss", 'L2 Hit': "HIT" if r.l2_hit else "miss", 'L3 Hit': "HIT" if r.l3_hit else "miss", 'Max Drawdown': f"{r.max_drawdown_pct:.1f}%"})
                            st.dataframe(pd.DataFrame(rows), use_container_width=True)
                            import csv as _csv, io as _io
                            from dataclasses import fields as _fields
                            csv_buf = _io.StringIO()
                            writer = _csv.DictWriter(csv_buf, fieldnames=[f.name for f in _fields(bt_results[0])])
                            writer.writeheader()
                            for r in bt_results:
                                writer.writerow({f.name: getattr(r, f.name) for f in _fields(r)})
                            st.download_button(label="Download CSV", data=csv_buf.getvalue(), file_name=f"{ticker}_backtest_{str(bt_start).replace('-','')}.csv", mime="text/csv")
