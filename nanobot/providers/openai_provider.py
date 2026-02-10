"""OpenAI SDK provider implementation for direct OpenAI API access."""

import json
from typing import Any

from openai import AsyncOpenAI
from loguru import logger

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class OpenAIProvider(LLMProvider):
    """
    LLM provider using the official OpenAI Python SDK.
    
    Supports OpenAI models and any OpenAI-compatible API endpoints
    (e.g., vLLM, DeepSeek, Moonshot, Zhipu, local servers) directly
    via the openai SDK without the litellm abstraction layer.
    """
    
    def __init__(
        self, 
        api_key: str | None = None, 
        api_base: str | None = None,
        default_model: str = "gpt-4o",
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        
        # Build AsyncOpenAI client
        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if api_base:
            client_kwargs["base_url"] = api_base
        
        self.client = AsyncOpenAI(**client_kwargs)
        logger.debug(
            f"OpenAIProvider initialized: model={default_model}, "
            f"base_url={api_base or 'default'}"
        )
    
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Send a chat completion request via the OpenAI SDK.
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'gpt-4o', 'deepseek-chat').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
        
        Returns:
            LLMResponse with content and/or tool calls.
        """
        model = model or self.default_model
        
        # Strip common provider prefixes so the raw model name is sent to the API.
        # e.g. "openai/gpt-4o" -> "gpt-4o", "deepseek/deepseek-chat" -> "deepseek-chat"
        for prefix in ("openai/", "deepseek/", "moonshot/", "zhipu/", "zai/"):
            if model.startswith(prefix):
                model = model[len(prefix):]
                break
        
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        try:
            response = await self.client.chat.completions.create(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"OpenAI SDK error: {e}")
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )
    
    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse OpenAI SDK response into our standard format."""
        choice = response.choices[0]
        message = choice.message
        
        tool_calls: list[ToolCallRequest] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))
        
        usage: dict[str, int] = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )
    
    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model
