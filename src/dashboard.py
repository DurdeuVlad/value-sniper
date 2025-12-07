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
ticker = st.sidebar.text_input("Ticker Symbol", value="MSFT").upper()
timeframe = st.sidebar.selectbox("Lookback Period", ["6mo", "1y", "2y", "5y", "max"], index=1)
use_cache = st.sidebar.checkbox("Use Cache", value=True)
enable_ai = st.sidebar.checkbox("Enable AI Analysis", value=False)
run_btn = st.sidebar.button("Run Analysis")

# Main Content
st.title(f"Sniper Analysis: {ticker}")

if run_btn:
    with st.spinner(f"Analyzing {ticker}..."):
        # Setup AI
        ai_provider = None
        if enable_ai:
            try:
                ai_provider = GeminiProvider()
            except ValueError:
                st.sidebar.error("GEMINI_API_KEY not found in .env")
        
        # Run the Bot
        bot = TechSniperAI(ticker, use_cache=use_cache, llm_provider=ai_provider, lookback_period=timeframe)
        orders = bot.generate_orders()
        
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
                        formatted_analysis += f"* {k}: {v}\n\n"
                    clean_analysis = re.sub(r'\*\*|__', '', formatted_analysis)
                else:
                    clean_analysis = re.sub(r'\*\*|__', '', str(raw_analysis))
                
                st.info(f"**🤖 AI Strategic Analysis:**\n\n{clean_analysis}")

            # --- 1. KEY LEVELS (Top Metrics) ---
            # Dynamic columns based on active levels (handles Defensive Shifts/Renaming)
            sorted_orders = sorted(orders.items(), key=lambda x: x[1], reverse=True)
            cols = st.columns(len(sorted_orders))
            
            for i, (label, price) in enumerate(sorted_orders):
                cols[i].metric(label, f"${price:.2f}")
            
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
            for label, price in orders.items():
                color = 'blue' # Default
                if 'Level 1' in label: color = 'orange'
                elif 'Level 2' in label: color = 'green'
                elif 'Level 3' in label: color = 'red'
                elif 'Disaster' in label: color = 'darkred'
                
                fig.add_hline(y=price, line_dash="dash", line_color=color, annotation_text=label, annotation_position="bottom right")

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
            tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Options Intelligence", "Macro Regime", "Market Fear", "Market Breadth", "Trend Strength", "Momentum (RSI)", "AI Logic"])
            
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
                raw_signals = [x for x in bot.potential_supports if x < bot.current_price]
                final_orders = list(orders.values())
                
                # Jitter for display
                jitter = np.random.uniform(-0.1, 0.1, size=len(raw_signals))
                
                fig_ai = go.Figure()
                fig_ai.add_trace(go.Scatter(x=raw_signals, y=jitter, mode='markers', name='Raw Signals', marker=dict(color='blue', size=10)))
                fig_ai.add_trace(go.Scatter(x=final_orders, y=[0]*len(final_orders), mode='markers', name='Final Orders', marker=dict(symbol='star', color='red', size=20)))
                
                fig_ai.update_yaxes(visible=False)
                fig_ai.update_layout(title="K-Means Clustering Visualization", template="plotly_dark", height=300)
                st.plotly_chart(fig_ai, use_container_width=True)
                
                if enable_ai:
                    ai_insight = ai_report.get('clustering_insight', 'Unavailable')
                    if ai_insight and ai_insight != "Unavailable":
                        st.success(f"🤖 **AI Insight:** {ai_insight}")

                st.info("**WHAT IS THIS?** The 'Brain' of the algorithm. BLUE DOTS = Every potential support found (Gaps, Moving Averages, Option Strikes). RED STARS = The consensus. The AI groups the Blue Dots and finds the center. Note: Blue dots are jittered vertically to show overlaps.")
