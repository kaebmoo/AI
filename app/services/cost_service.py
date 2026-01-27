from typing import Dict, Optional
from app.config import settings

class CostService:
    """
    Service to calculate AI API costs based on token usage.
    """
    
    # Pricing per 1M tokens (approximate, adjust as needed)
    PRICING = {
        "claude-3-sonnet-20240229": {
            "input": 3.00,  # $3 per 1M input tokens
            "output": 15.00 # $15 per 1M output tokens
        },
        "claude-3-opus-20240229": {
            "input": 15.00,
            "output": 75.00
        },
        "gemini-1.5-pro": {
             "input": 3.50,
             "output": 10.50
        },
        "gemini-1.0-pro": {
            "input": 0.50,
            "output": 1.50
        }
    }
    
    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost in USD
        """
        # Default to generic pricing if model not found
        pricing = self.PRICING.get(model, {"input": 10.0, "output": 30.0})
        
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        
        return round(input_cost + output_cost, 6)

    def estimate_tokens(self, text: str) -> int:
        """
        Rough estimate of tokens (4 chars per token)
        """
        return len(text) // 4
