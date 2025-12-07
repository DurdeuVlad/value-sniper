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
        Batches all analysis requests into a single API call to prevent rate limiting.
        """
        prompt = f"""
        You are a Wall Street Quantitative Analyst. Analyze the following multi-dimensional market data for {data_package.get('ticker', 'Unknown')}.
        
        === INPUT DATA ===
        1. CORE ORDERS: {data_package.get('orders')}
        2. PROTOCOL LOGS: {data_package.get('logs')}
        3. OPTIONS DATA: {data_package.get('options_context')}
        4. MACRO DATA: {data_package.get('macro_context')}
        5. VIX DATA: {data_package.get('vix_context')}
        6. BREADTH DATA: {data_package.get('breadth_context')}
        7. TREND DATA: {data_package.get('trend_context')}
        8. RSI DATA: {data_package.get('rsi_context')}
        9. CLUSTERING DATA: {data_package.get('clustering_context')}
        
        === TASK ===
        Provide a structured analysis in JSON format with the following keys:
        
        - "strategic_analysis": A comprehensive summary (Regime, Support Levels, Recommendation). Keep it professional and concise (bullet points). Plain text only (no markdown).
        - "options_insight": 1-2 sentence specific insight on the Options data (Focus on Max Pain/Walls).
        - "macro_insight": 1-2 sentence insight on the Macro Yields (Bullish/Bearish for Tech).
        - "vix_insight": 1-2 sentence insight on VIX (Fear/Complacency).
        - "breadth_insight": 1-2 sentence insight on SPY vs RSP divergence.
        - "trend_insight": 1-2 sentence insight on ADX (Trend Strength vs Chop).
        - "rsi_insight": 1-2 sentence insight on RSI (Momentum/Divergence).
        - "clustering_insight": 1-2 sentence insight on the reliability of the clusters.
        
        Output MUST be valid JSON. Do not use Markdown code blocks.
        """
        
        response_text = self._generate_with_retry(prompt, progress_callback=progress_callback)
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "strategic_analysis": "Error parsing AI response.",
                "options_insight": "Unavailable",
                "macro_insight": "Unavailable",
                "vix_insight": "Unavailable",
                "breadth_insight": "Unavailable",
                "trend_insight": "Unavailable",
                "rsi_insight": "Unavailable",
                "clustering_insight": "Unavailable"
            }

    # Legacy methods kept for compatibility but unused in new flow
    def analyze(self, ticker: str, price: float, orders: dict, logs: dict, progress_callback=None) -> str:
        return "Use generate_full_report instead."

    def explain_chart(self, chart_type: str, data_context: str, progress_callback=None) -> str:
        return "Use generate_full_report instead."
