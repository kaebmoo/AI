
import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.insert(0, os.getcwd())

# Mock google.genai
sys.modules["google"] = MagicMock()
sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()
sys.modules["google.genai.models"] = MagicMock()

# Setup Mock Types
from google.genai import types

class MockPart:
    def __init__(self, text=None, function_call=None, function_response=None, thought=None):
        self.text = text
        self.function_call = function_call
        self.function_response = function_response
        self.thought = thought # Simulate internal thought field
        
    def to_dict(self):
        d = {}
        if self.text: d['text'] = self.text
        if self.function_call: 
            d['function_call'] = self.function_call
        if self.thought is not None:
             # Simulate that to_dict MIGHT NOT include thought if it's internal
             # OR it does. Let's assume it does for now to test successful path.
             # If this fails in real life, we know to_dict is insufficient.
             d['thought'] = self.thought
        return d
    
    @classmethod
    def from_dict(cls, d):
        return cls(
            text=d.get('text'),
            function_call=d.get('function_call'),
            thought=d.get('thought')
        )

types.Part = MockPart
types.Part.from_dict = MockPart.from_dict
types.Content = MagicMock
types.FunctionCall = MagicMock
types.FunctionResponse = MagicMock
types.GenerateContentConfig = MagicMock

# Import Provider
from app.services.ai_service import GeminiProvider

async def test_gemini_part_preservation():
    print("Testing Gemini Part Preservation...")
    
    # Setup Provider
    provider = GeminiProvider(api_key="fake", model="gemini-test")
    provider._client = MagicMock()
    provider._client.models.generate_content = MagicMock()
    provider._run_async = AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs))

    # Scenario: 
    # History contains a Model Turn that was previously saved with 'parts_raw'
    # We want to check if generate_sql correctly reconstructs it using parts_raw
    
    # 1. Simulate capture phase (what happens in query_with_retry)
    original_part = MockPart(function_call={"name": "foo", "args": {}}, thought=True)
    parts_raw = [original_part.to_dict()]
    
    print(f"Captured parts_raw: {parts_raw}")
    
    # 2. Simulate history passed to generate_sql
    history = [
        {"role": "user", "content": "Hi"},
        {
            "role": "model", 
            "parts_raw": parts_raw, 
            "internal_id": "__gemini_model_turn_0__"
        },
        {"role": "function", "name": "foo", "content": {"result": "bar"}} # Response
    ]
    
    # 3. Call generate_sql
    await provider.generate_sql(question=None, system_prompt="Sys", tools=[], history=history)
    
    # 4. Inspect calls
    call_args = provider.client.models.generate_content.call_args
    if not call_args:
        print("FAIL: generate_content was not called")
        return

    contents = call_args[1]['contents']
    print("\n--- Generated Contents Payload ---")
    
    model_content = contents[1] # [0]=User, [1]=Model, [2]=Tool
    assert model_content.role == "model"
    
    reconstructed_part = model_content.parts[0]
    
    print(f"Reconstructed Part: {reconstructed_part.__dict__}")
    
    if reconstructed_part.thought is True:
        print("SUCCESS: Thought signature was preserved via parts_raw -> from_dict")
    else:
        print("FAIL: Thought signature was LOST")

if __name__ == "__main__":
    asyncio.run(test_gemini_part_preservation())
