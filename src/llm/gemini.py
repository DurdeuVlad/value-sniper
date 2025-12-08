import os
import time
import random
import re
import json
import google.generativeai as genai
from .base import LLMProvider

class GeminiProvider(LLMProvider):
    def __init__(self, api_key=None, model_name="gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model_name, generation_config={"response_mime_type": "application/json"})

    def _generate_with_retry(self, prompt, max_retries=5, progress_callback=None):
        """Helper to handle Rate Limits with smart backoff."""
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                err_str = str(e)
                sleep_time = 0
                
                # Check for specific retry instruction
                match = re.search(r"retry in (\d+\.?\d*)s", err_str)
                if match:
                    sleep_time = float(match.group(1)) + 2.0 # Add 2s buffer
                    print(f"[AI RATE LIMIT] Quota exceeded. Waiting {sleep_time:.2f}s as requested...")
                else:
                    # Exponential Backoff: 2, 4, 8, 16...
                    sleep_time = (2 ** attempt) + (random.random() * 2)
                    print(f"[AI ERROR] Attempt {attempt+1} failed: {e}. Retrying in {sleep_time:.2f}s...")
                
                # Countdown Loop
                for remaining in range(int(sleep_time), 0, -1):
                    msg = f"Rate Limit Hit. Retrying in {remaining}s..."
                    if progress_callback:
                        progress_callback(msg)
                    time.sleep(1)
                time.sleep(sleep_time % 1) # Sleep remaining float fraction
        
        return "{}" # Return empty JSON string on failure

    def generate_full_report(self, data_package, progress_callback=None) -> dict:
        """
        Generate comprehensive market analysis with actual insights, not corporate speak.
        """
        ticker = data_package.get('ticker', 'Unknown')
        orders = data_package.get('orders', {})
        
        # Extract key metrics from orders
        levels = sorted([(k, v) for k, v in orders.items()], key=lambda x: x[1]['price'], reverse=True)
        l1_price = levels[0][1]['price'] if len(levels) > 0 else 0
        l1_drop = levels[0][1]['percent_drop'] if len(levels) > 0 else 0
        l1_pe = levels[0][1]['estimated_pe'] if len(levels) > 0 else 0
        l1_ps = levels[0][1]['estimated_ps'] if len(levels) > 0 else 0
        
        l2_price = levels[1][1]['price'] if len(levels) > 1 else 0
        l2_drop = levels[1][1]['percent_drop'] if len(levels) > 1 else 0
        l2_pe = levels[1][1]['estimated_pe'] if len(levels) > 1 else 0
        l2_ps = levels[1][1]['estimated_ps'] if len(levels) > 1 else 0
        
        l3_price = levels[2][1]['price'] if len(levels) > 2 else 0
        l3_drop = levels[2][1]['percent_drop'] if len(levels) > 2 else 0
        l3_pe = levels[2][1]['estimated_pe'] if len(levels) > 2 else 0
        l3_ps = levels[2][1]['estimated_ps'] if len(levels) > 2 else 0
        
        # Extract protocol data
        options_data = data_package.get('options_context', 'N/A')
        breadth_data = data_package.get('breadth_context', 'N/A')
        rsi_data = data_package.get('rsi_context', 'N/A')
        vix_data = data_package.get('vix_context', 'N/A')
        sector_data = data_package.get('clustering_context', 'N/A')
        risk_score = data_package.get('logs', {}).get('Risk Score', 'N/A')
        
        # Determine if defensive shift is active
        defensive_mode = 'Conservative Entry' in str(levels[0][0]) if levels else False
        
        prompt = f"""You are a direct, no-BS quantitative analyst. Give ACTIONABLE insights, not corporate platitudes.

TICKER: {ticker}

KEY SIGNALS:
- Breadth: {breadth_data}
- Sector: {sector_data}
- RSI: {rsi_data}
- VIX: {vix_data}
- Options: {options_data}
- Risk Score: {risk_score}
- Mode: {"DEFENSIVE (Narrow Rally Detected)" if defensive_mode else "STANDARD (Healthy Market)"}

SUPPORT LEVELS & VALUATIONS:
- L1: ${l1_price:.2f} (-{l1_drop:.1f}%) → P/E: {l1_pe:.1f}, P/S: {l1_ps:.1f}
- L2: ${l2_price:.2f} (-{l2_drop:.1f}%) → P/E: {l2_pe:.1f}, P/S: {l2_ps:.1f}
- L3: ${l3_price:.2f} (-{l3_drop:.1f}%) → P/E: {l3_pe:.1f}, P/S: {l3_ps:.1f}

YOUR TASK: Write a 300-500 word analysis covering:

1. MARKET STRUCTURE WARNING (if applicable)
   - If defensive mode is active, explain what "narrow rally" means for THIS stock
   - Compare breadth divergence to historical patterns (2018, 2020, 2022)
   - Be specific about the actual RISK (not "underlying risk")

2. VALUATION SWEET SPOT
   - Which level offers the best risk/reward based on P/E and P/S?
   - Is the valuation premium justified? What needs to happen for multiples to compress?
   - Compare valuations across levels - where is the "fair value"?

3. OPTIONS INTELLIGENCE  
   - Parse the max pain data - is it above or below current price?
   - How many days to expiry? Is this relevant NOW or later?
   - What does this tell us about where market makers expect the stock to go?

4. TACTICAL ALLOCATION
   - Should user stick to 20-30-50 or adjust based on signals?
   - Which level is the PRIMARY target vs "nice to have"?
   - Scenario-based: "If breadth improves → do X, if it deteriorates → do Y"

5. RISK SCENARIOS
   - BEST CASE: What happens if market structure improves?
   - BASE CASE: Normal correction - which levels fill?
   - WORST CASE: Structure breaks completely - is L3 safe?

6. ONE KEY INSIGHT (2-3 sentences max)
   - The MOST important thing the user needs to know about this setup
   - Make it memorable and actionable

WRITING STYLE:
- Use emojis for section headers (🚨 💰 🎯 📊 ⚠️)
- Write in SHORT paragraphs (2-4 sentences max)
- Be DIRECT: "This is expensive" not "valuation appears elevated"
- Cite SPECIFIC numbers from the data
- NO corporate speak or hedge words
- Write in prose, NOT bullet points

OUTPUT FORMAT:
Return valid JSON with single key "strategic_analysis" containing your full analysis.
Use actual line breaks in the JSON string, not escape sequences.
Format the text naturally as you would write it, with blank lines between sections.
Do NOT use markdown bold, italics, or other formatting.
Just plain text with emojis and paragraphs.

Example structure:
{{
  "strategic_analysis": "🚨 MARKET STRUCTURE WARNING\n\nThe narrow rally warning is real here. Tech sector is strong but breadth is collapsing.\n\n💰 VALUATION SWEET SPOT\n\nAt L2, you're paying a reasonable multiple..."
}}
"""
        
        response_text = self._generate_with_retry(prompt, progress_callback=progress_callback)
        
        try:
            result = json.loads(response_text)
            # If strategic_analysis exists, return it properly formatted
            if 'strategic_analysis' in result:
                # Clean up any escape sequences in the text
                analysis_text = result['strategic_analysis']
                # Replace literal \n with actual newlines
                analysis_text = analysis_text.replace('\\n', '\n')
                result['strategic_analysis'] = analysis_text
                return result
            else:
                return {"strategic_analysis": response_text}
        except json.JSONDecodeError as e:
            # If JSON parsing fails, return the raw text
            print(f"[AI] JSON decode error: {e}. Returning raw text.")
            return {"strategic_analysis": f"Analysis generated:\n\n{response_text}"}

    # Legacy methods kept for compatibility but unused in new flow
    def analyze(self, ticker: str, price: float, orders: dict, logs: dict, progress_callback=None) -> str:
        return "Use generate_full_report instead."

    def explain_chart(self, chart_type: str, data_context: str, progress_callback=None) -> str:
        return "Use generate_full_report instead."
