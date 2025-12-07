import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np
import os

class SniperPlotter:
    def __init__(self, sniper_bot, runtime_dir="_runtime"):
        self.bot = sniper_bot
        self.runtime_dir = runtime_dir
        if not os.path.exists(self.runtime_dir):
            os.makedirs(self.runtime_dir)

    def _add_explanation(self, fig, text):
        """Adds a footer text box to the figure."""
        plt.figtext(0.5, 0.02, text, ha="center", fontsize=9, 
                    bbox={"facecolor":"orange", "alpha":0.1, "pad":5}, wrap=True)
        plt.subplots_adjust(bottom=0.2) # Make room for text

    def plot_options_chain(self):
        """Generates a bar chart for Options Open Interest (The Smile)."""
        if not hasattr(self.bot, 'df_pain') or self.bot.df_pain.empty:
            return

        print(f"Generating Options visualization...")
        df = self.bot.df_pain
        
        # Filter for relevant range (near current price)
        center_price = self.bot.current_price
        df = df[(df['Strike'] > center_price * 0.8) & (df['Strike'] < center_price * 1.2)]
        
        fig, ax = plt.subplots(figsize=(10, 7))
        
        width = 2.0  # Bar width, adjust based on strike interval if needed
        
        ax.bar(df['Strike'], df['Call_OI'], width=width, label='Calls (Betting UP)', color='green', alpha=0.6)
        ax.bar(df['Strike'], df['Put_OI'], width=width, label='Puts (Betting DOWN)', color='red', alpha=0.6, bottom=df['Call_OI'])
        
        ax.set_title(f"{self.bot.ticker} Options Open Interest Structure")
        ax.set_xlabel("Strike Price")
        ax.set_ylabel("Open Interest")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        explanation = (
            "WHAT IS THIS? A map of the 'Casino's Liability'.\n"
            "Tall Bars = Heavy Betting. The Market Makers want these bets to expire worthless.\n"
            "If you see a massive Green Tower at a price, the stock will struggle to go above it (Resistance).\n"
            "The Algorithm hunts for the price that causes the 'Max Pain' to the most traders."
        )
        self._add_explanation(fig, explanation)
        
        filename = os.path.join(self.runtime_dir, f"{self.bot.ticker}_options_structure.png")
        plt.savefig(filename)
        plt.close()
        print(f"Options chart saved to: {filename}")

    def plot_macro_regime(self):
        """Visualizes the 10-Year Yield (TNX) and its Bollinger Bands."""
        if self.bot.tnx.empty: return
        
        print("Generating Macro visualization...")
        df = self.bot.tnx.iloc[-120:].copy() # Last 6 months
        
        # Recalculate BB for plotting
        window = 20
        df['SMA'] = df['Close'].rolling(window=window).mean()
        df['STD'] = df['Close'].rolling(window=window).std()
        df['Upper'] = df['SMA'] + (df['STD'] * 2)
        
        fig, ax = plt.subplots(figsize=(10, 7))
        
        ax.plot(df.index, df['Close'], label='10-Year Yield (^TNX)', color='black')
        ax.plot(df.index, df['Upper'], label='Upper BB (2 Std Dev)', color='red', linestyle='--')
        ax.fill_between(df.index, df['Upper'], df['Close'], where=(df['Close'] > df['Upper']), color='red', alpha=0.3, label='Panic Zone (Buy Signal)')
        
        ax.set_title("Macro Protocol: Yield Sensitivity Model")
        ax.set_ylabel("Yield (%)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        explanation = (
            "WHAT IS THIS? A gauge of Interest Rate Stress.\n"
            "Tech stocks move OPPOSITE to rates. When Rates (Black Line) hit the Red Line, it means bonds are oversold.\n"
            "SIGNAL: If Black Line > Red Line --> BUY TECH (Expect a rate reversion).\n"
            "SIGNAL: If Black Line < Red Line --> NEUTRAL (Normal market conditions)."
        )
        self._add_explanation(fig, explanation)

        filename = os.path.join(self.runtime_dir, f"{self.bot.ticker}_macro_regime.png")
        plt.savefig(filename)
        plt.close()
        print(f"Macro chart saved to: {filename}")

    def plot_clustering_logic(self, orders):
        """Visualizes how raw signals were grouped into 3 orders using K-Means."""
        if not self.bot.potential_supports: return
        
        print("Generating Clustering Logic visualization...")
        
        raw_signals = [x for x in self.bot.potential_supports if x < self.bot.current_price]
        final_orders = list(orders.values())
        
        fig, ax = plt.subplots(figsize=(10, 5))
        
        # Add Jitter to Y-axis for Raw Signals so they don't overlap
        # We create a small random y-offset for each point
        jitter = np.random.uniform(-0.05, 0.05, size=len(raw_signals))
        
        # Plot Raw Signals (Blue Dots)
        ax.scatter(raw_signals, jitter, color='blue', alpha=0.5, s=100, label='Raw Signals (Gaps, Options, MA)')
        
        # Plot Final Centers (Red Stars) - Plot at Y=0
        ax.scatter(final_orders, [0]*len(final_orders), color='red', marker='*', s=300, label='Final AI Clusters (The Orders)')
        
        ax.set_yticks([]) # Hide Y axis
        ax.set_title(f"AI Logic: K-Means Clustering ({len(raw_signals)} Signals -> 3 Orders)")
        ax.set_xlabel("Price ($)")
        ax.legend()
        ax.grid(True, axis='x', alpha=0.3)
        
        # Add Sector Regime Badge
        sector_status = self.bot.runtime_log.get('Sector Protocol', 'Unknown')
        # Extract just the SIGNAL part if possible, otherwise show full string
        if "SIGNAL:" in sector_status:
            sector_status = sector_status.split("SIGNAL:")[1].strip()
        
        regime_color = 'green' if 'STRONG' in sector_status else 'red'
        plt.figtext(0.13, 0.83, f"SECTOR REGIME: {sector_status}", fontsize=10, weight='bold',
                    color='white', bbox=dict(facecolor=regime_color, alpha=0.8, boxstyle='round,pad=0.5'))
        
        explanation = (
            "WHAT IS THIS? The 'Brain' of the algorithm.\n"
            "BLUE DOTS = Every potential support found (Unfilled Gaps, Moving Averages, Option Strikes).\n"
            "RED STARS = The consensus. The AI groups the Blue Dots and finds the center.\n"
            "NOTE: Overlapping Blue Dots are 'jittered' vertically so you can see them all."
        )
        self._add_explanation(fig, explanation)
        
        filename = os.path.join(self.runtime_dir, f"{self.bot.ticker}_clustering_logic.png")
        plt.savefig(filename)
        plt.close()
        print(f"Clustering chart saved to: {filename}")

    def plot_sniper_view(self, orders):
        """Generates a comprehensive visualization of the sniper analysis."""
        
        # 1. Trigger Sub-Charts
        self.plot_options_chain()
        self.plot_macro_regime()
        self.plot_clustering_logic(orders)

        print(f"Generating visualization in {self.runtime_dir}...")
        
        # Prepare Data for Plotting
        # We need a slice of data, maybe last 6 months for context
        plot_df = self.bot.df.iloc[-120:].copy() # Last ~6 months
        
        # Calculate RSI for plotting if not present
        if 'RSI' not in plot_df.columns:
            # Re-calc locally if needed
            delta = plot_df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).fillna(0)
            loss = (-delta.where(delta < 0, 0)).fillna(0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss
            plot_df['RSI'] = 100 - (100 / (1 + rs))

        ap = []
        
        # Color codes for levels
        colors = {
            "Level 1 (Aggressive)": 'orange',
            "Level 1 (Aggressive - HIGH RSI RISK)": 'orange',
            "Level 2 (Deep Value)": 'green',
            "Level 3 (Capitulation)": 'red',
            "Level 1 (Value - Shifted)": 'green',
            "Level 2 (Capitulation - Shifted)": 'red',
            "Level 3 (Disaster/3-Sigma)": 'darkred'
        }
        
        # Add support lines (Panel 0 - Main)
        for label, price in orders.items():
            if price < plot_df['Close'].min() * 0.5: continue # Skip if way off chart
            line_data = [price] * len(plot_df)
            color = colors.get(label, 'blue')
            ap.append(mpf.make_addplot(line_data, color=color, linestyle='--', width=1.5, panel=0))

        # Add SMA 200 (Panel 0)
        if len(self.bot.df) > 200:
             sma200 = self.bot.df['Close'].rolling(200).mean().iloc[-120:]
             ap.append(mpf.make_addplot(sma200, color='purple', width=1, panel=0))

        # Add RSI (Panel 1)
        ap.append(mpf.make_addplot(plot_df['RSI'], panel=1, color='black', ylabel='RSI', width=1.2))
        # RSI Bounds
        ap.append(mpf.make_addplot([70]*len(plot_df), panel=1, color='red', linestyle=':', width=1))
        ap.append(mpf.make_addplot([30]*len(plot_df), panel=1, color='green', linestyle=':', width=1))

        # 2. Setup the Style
        mc = mpf.make_marketcolors(up='green', down='red', inherit=True)
        s  = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=True)

        # 3. Generate Plot
        filename = os.path.join(self.runtime_dir, f"{self.bot.ticker}_sniper_analysis.png")
        
        # Get Sector Status for Title
        sector_status = self.bot.runtime_log.get('Sector Protocol', 'Unknown')
        if "SIGNAL:" in sector_status:
            sector_status = sector_status.split("SIGNAL:")[1].strip()
        
        # Create a custom title with the level details
        title = f"\n{self.bot.ticker} Sniper Analysis [{sector_status}]\n"
        for k, v in orders.items():
            short_label = k.split('(')[0].strip() # Shorten label for title
            title += f"{short_label}: ${v:.2f} | "
            
        try:
            mpf.plot(plot_df, 
                     type='candle', 
                     volume=True, 
                     addplot=ap, 
                     style=s, 
                     title=title,
                     savefig=filename,
                     figsize=(12, 10), # Taller for RSI panel
                     panel_ratios=(3,1), # Main chart 3x taller than RSI
                     tight_layout=True)
            
            print(f"Visualization saved to: {filename}")
        except Exception as e:
            print(f"Error generating plot: {e}")

    def log_steps(self, steps_data):
        """Writes a detailed step-by-step log to a text file."""
        log_path = os.path.join(self.runtime_dir, f"{self.bot.ticker}_calculation_log.txt")
        with open(log_path, "w") as f:
            f.write(f"--- SNIPER CALCULATION LOG: {self.bot.ticker} ---\n")
            f.write(f"Current Price: ${self.bot.current_price:.2f}\n\n")
            
            for step_name, details in steps_data.items():
                f.write(f"=== {step_name} ===\n")
                if isinstance(details, list):
                    for item in details:
                        f.write(f" - {item}\n")
                elif isinstance(details, dict):
                    for k, v in details.items():
                        f.write(f" - {k}: {v}\n")
                else:
                    f.write(f" - {details}\n")
                f.write("\n")
        
        print(f"Calculation log saved to: {log_path}")
