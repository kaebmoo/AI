from typing import Optional

from app.config import settings
from app.providers.claude_provider import ClaudeProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.matcha_provider import MatchaProvider
from app.services.ai.service import AIService
from app.services.mcp_client import MCPClientService


def create_claude_service(
    api_key: str,
    mcp_client: MCPClientService = None,
    model: Optional[str] = None,
    extended_thinking: bool = False,
    thinking_budget_tokens: int = 8000,
    **kwargs,
) -> AIService:
    del kwargs

    provider = ClaudeProvider(
        api_key=api_key,
        model=model or settings.CLAUDE_MODEL,
        extended_thinking=extended_thinking,
        thinking_budget_tokens=thinking_budget_tokens,
    )
    return AIService(provider=provider, mcp_client=mcp_client)


def create_gemini_service(
    api_key: str,
    mcp_client: MCPClientService = None,
    model: Optional[str] = None,
    **kwargs,
) -> AIService:
    del kwargs

    provider = GeminiProvider(
        api_key=api_key,
        model=model or settings.GEMINI_MODEL,
    )
    return AIService(provider=provider, mcp_client=mcp_client)


def create_matcha_service(
    api_key: str,
    api_url: str = None,
    mcp_client: MCPClientService = None,
    model: Optional[str] = None,
    **kwargs,
) -> AIService:
    del kwargs

    provider = MatchaProvider(
        api_key=api_key,
        api_url=api_url or settings.MATCHA_API_URL or "",
        model=model or settings.MATCHA_MODEL,
    )
    return AIService(provider=provider, mcp_client=mcp_client)