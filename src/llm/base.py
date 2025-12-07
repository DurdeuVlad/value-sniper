from abc import ABC, abstractmethod

class LLMProvider(ABC):
    """Abstract Base Class for AI/LLM Providers."""
    
    @abstractmethod
    def analyze(self, ticker: str, price: float, orders: dict, logs: dict, progress_callback=None) -> str:
        """
        Analyzes the technical context and returns a strategic summary.
        
        Args:
            ticker: Stock symbol (e.g., 'MSFT')
            price: Current price
            orders: The calculated support levels
            logs: The runtime logs containing protocol signals (RSI, Sector, etc.)
            progress_callback: Function to call with status updates string.
            
        Returns:
            str: The text analysis from the AI.
        """
        pass

    @abstractmethod
    def explain_chart(self, chart_type: str, data_context: str, progress_callback=None) -> str:
        """
        Generates a specific explanation for a single chart type.
        
        Args:
            chart_type: 'options', 'macro', or 'clustering'
            data_context: String summary of the specific data for that chart.
            progress_callback: Function to call with status updates string.
            
        Returns:
            str: Brief 1-2 sentence insight.
        """
        pass
