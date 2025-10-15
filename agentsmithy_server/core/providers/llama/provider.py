"""Llama provider implementation for local chat models.

This module contains `LlamaProvider`, which provides local Llama model support
via llama.cpp through LangChain's ChatLlamaCpp interface.

For models without native function calling (like Qwen), this provider parses
JSON tool calls from the model's text response and converts them to proper
tool_calls format.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from importlib import import_module
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from agentsmithy_server.config import settings
from agentsmithy_server.core.providers.llama.adapter import LlamaChatAdapter
from agentsmithy_server.utils.logger import agent_logger


def parse_tool_call_from_text(text: str) -> dict | None:
    """Extract JSON tool call from model's text response.
    
    Handles two cases:
    1. Proper format: {"name": "tool_name", "arguments": {...}}
    2. Direct JSON (for return_inspection): {"primary_languages": [...], ...}
    
    Returns:
        - dict with 'name' and 'arguments' if valid tool call found
        - dict with 'error' if JSON found but invalid
        - None if no JSON found at all
    """
    if not text:
        return None
    
    # Patterns to try (in order of preference)
    patterns = [
        r'```json\s*(\{[^`]+\})\s*```',  # JSON in markdown
        r'```\s*(\{[^`]+\})\s*```',       # JSON without language specifier
        r'(\{\s*"[^"]+"\s*:)',            # Any JSON object
    ]
    
    json_str = None
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
        if match:
            # For the last pattern, we need to extract full JSON
            if pattern == r'(\{\s*"[^"]+"\s*:)':
                # Find the full JSON object starting from this point
                start_pos = match.start()
                candidate = text[start_pos:]
                # Try to find the end of JSON
                brace_count = 0
                end_pos = 0
                for i, char in enumerate(candidate):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1
                            break
                if end_pos > 0:
                    json_str = candidate[:end_pos]
            else:
                json_str = match.group(1)
            
            if json_str:
                break
    
    if not json_str:
        return None
    
    # Try to parse JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        # Return error info so model can retry
        return {
            "error": f"Invalid JSON: {str(e)}. Check for syntax errors (missing commas, extra brackets, etc.)"
        }
    
    # Case 1: Proper tool call format
    if "name" in data:
        return {
            "name": data["name"],
            "arguments": data.get("arguments", data.get("args", {}))
        }
    
    # Case 2: Direct JSON for return_inspection 
    # (has inspection-specific fields)
    if any(key in data for key in ["primary_languages", "frameworks", "build_tooling"]):
        agent_logger.debug(
            "Detected direct JSON response, treating as return_inspection call"
        )
        
        # Adapt model's format to expected schema
        adapted_args = {
            "language": data.get("primary_languages", ["unknown"])[0] if data.get("primary_languages") else "unknown",
            "frameworks": data.get("frameworks", []),
            "package_managers": data.get("package_managers", data.get("build_tooling", [])),
            "build_tools": data.get("build_tools", data.get("build_tooling", [])),
            "architecture_hints": data.get("architecture_hints", [])
        }
        
        # Extract architecture hints from architectural_structure if present
        arch_struct = data.get("architectural_structure", {})
        if isinstance(arch_struct, dict):
            modules = arch_struct.get("modules", [])
            if modules:
                adapted_args["architecture_hints"] = modules[:10]  # Limit to 10
        
        # Add other_tools to build_tools if present
        other_tools = data.get("other_tools", [])
        if other_tools:
            adapted_args["build_tools"].extend(other_tools)
        
        return {
            "name": "return_inspection",
            "arguments": adapted_args
        }
    
    # Found JSON but doesn't match expected formats
    return None


class LlamaProvider:
    """Local Llama LLM provider implementation via llama.cpp.

    Provides the same interface as other providers for consistency.
    """

    def __init__(
        self,
        model_path: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        n_ctx: int | None = None,
        n_threads: int | None = None,
        agent_name: str | None = None,
    ):
        """Initialize Llama provider.

        Args:
            model_path: Path to .gguf model file
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            n_ctx: Context window size
            n_threads: Number of CPU threads to use
            agent_name: Optional agent name for config lookup
        """
        # Agent model selection via models.agents; default to universal unless agent_name given
        agents_cfg = settings._get("models.agents", {})
        if isinstance(agents_cfg, dict):
            agent_entry = (
                agents_cfg.get(agent_name)
                if agent_name
                else agents_cfg.get("universal")
            )
        else:
            agent_entry = None

        # Get llama provider config first (highest priority for model_path)
        prov_llama = settings.get_provider_config("llama")

        # Resolve model path: explicit param > agent config > provider config
        resolved_agent_model = (
            agent_entry.get("model") if isinstance(agent_entry, dict) else None
        )

        # Only use resolved_agent_model if it looks like a llama model path
        if resolved_agent_model and isinstance(resolved_agent_model, str):
            if not (resolved_agent_model.endswith(".gguf") or resolved_agent_model.startswith("llama:")):
                resolved_agent_model = None

        self.model_path = (
            model_path
            or resolved_agent_model
            or prov_llama.get("model_path")
            or settings._get("llama.model_path", None)
        )

        if not self.model_path:
            raise ValueError(
                "Llama model path not specified. Set 'providers.llama.model_path' "
                "or configure models.agents.<agent>.model with a .gguf file path"
            )

        # Configuration with fallbacks
        self.temperature = (
            temperature
            if temperature is not None
            else prov_llama.get("temperature", settings.temperature)
        )
        self.max_tokens = (
            max_tokens
            if max_tokens is not None
            else prov_llama.get("max_tokens", settings.max_tokens)
        )
        self.n_ctx = (
            n_ctx if n_ctx is not None else prov_llama.get("n_ctx", 8192)
        )
        self.n_threads = (
            n_threads if n_threads is not None else prov_llama.get("n_threads", 8)
        )

        agent_logger.info(
            "Initializing Llama provider",
            model_path=self.model_path,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
        )

        # Create adapter with model path (adapters registered by provider_factory)
        adapter = LlamaChatAdapter(self.model_path)
        class_path, kwargs = adapter.build_langchain(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort="",  # Not applicable for Llama
        )

        # Override with our specific settings
        kwargs["n_ctx"] = self.n_ctx
        kwargs["n_threads"] = self.n_threads
        kwargs["verbose"] = prov_llama.get("verbose", False)

        # Apply any additional options from provider config
        try:
            extra_opts = prov_llama.get("options") or {}
            if isinstance(extra_opts, dict) and extra_opts:
                kwargs.update(extra_opts)
        except Exception:
            pass

        module_path, class_name = class_path.rsplit(".", 1)
        cls = getattr(import_module(module_path), class_name)
        try:
            agent_logger.debug(
                "Initializing Llama chat model",
                class_path=class_path,
                kwargs_keys=list(kwargs.keys()),
            )
        except Exception:
            pass
        self.llm = cls(**kwargs)

        # Track last observed usage in streaming mode
        self._last_usage: dict[str, Any] | None = None

    async def agenerate(
        self, messages: list[BaseMessage], stream: bool = False, **kwargs
    ) -> AsyncIterator[str | dict[str, Any]] | str:
        """Generate response from messages.
        
        For non-streaming: parses JSON tool calls from content and converts
        them to proper AIMessage with tool_calls.
        
        For Llama/Qwen models, converts ToolMessage to HumanMessage with
        instruction to continue, since these models don't natively understand
        the ToolMessage format.
        """
        if stream:
            return self._agenerate_stream(messages, **kwargs)
        else:
            # Adapt messages for Llama: convert ToolMessage to HumanMessage
            adapted_messages = self._adapt_messages_for_llama(messages)
            
            response = await self.llm.ainvoke(adapted_messages, **kwargs)
            content = getattr(response, "content", "")
            
            # Try to parse tool call from content
            parse_result = parse_tool_call_from_text(content)
            
            if isinstance(parse_result, dict) and "error" in parse_result:
                # JSON parsing error - return as AIMessage with error in content
                # This allows the agent/executor to handle it
                agent_logger.warning(
                    "Failed to parse tool call from Llama response",
                    error=parse_result["error"],
                    content_preview=content[:200]
                )
                return AIMessage(
                    content=f"ERROR: Invalid JSON in response: {parse_result['error']}\n\nYour response: {content}"
                )
            
            if parse_result:
                # Found a tool call in the text - convert to proper format
                agent_logger.debug(
                    "Parsed tool call from Llama response",
                    tool_name=parse_result["name"],
                    has_args=bool(parse_result.get("arguments"))
                )
                
                # Create AIMessage with tool_calls (like in granite/main.py)
                import uuid
                tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
                
                ai_message = AIMessage(
                    content=content,
                    tool_calls=[{
                        "name": parse_result["name"],
                        "args": parse_result["arguments"],
                        "id": tool_call_id,
                    }]
                )
                return ai_message
            
            # No tool call found - return content as-is
            if isinstance(content, str):
                return content
            return str(content)

    async def _agenerate_stream(
        self, messages: list[BaseMessage], **kwargs
    ) -> AsyncIterator[str | dict[str, Any]]:
        """Generate streaming response."""
        async for chunk in self.llm.astream(messages, **kwargs):
            content = getattr(chunk, "content", None)
            if isinstance(content, str) and content:
                yield {"type": "chat", "content": content}

            # Track usage information from chunks if available
            try:
                usage = None
                add = getattr(chunk, "additional_kwargs", {}) or {}
                if isinstance(add, dict) and add.get("usage"):
                    usage = add.get("usage")

                meta = getattr(chunk, "response_metadata", {}) or {}
                if not usage and isinstance(meta, dict) and meta.get("token_usage"):
                    usage = meta.get("token_usage")

                um = getattr(chunk, "usage_metadata", None)
                if isinstance(um, dict) and um:
                    usage = um

                if usage:
                    self._last_usage = usage
            except Exception:
                pass

    def get_model_name(self) -> str:
        """Return model identifier (path for local models)."""
        return self.model_path

    def bind_tools(self, tools: list[BaseTool]) -> Any:
        """Bind tools to the model.

        Note: Llama models (especially Qwen) don't support native function calling.
        We return self so that ainvoke goes through our agenerate which has the
        JSON parser.
        """
        # Return self instead of self.llm so ainvoke calls our agenerate method
        # which has the JSON->tool_call parser
        return self

    def get_last_usage(self) -> dict[str, Any] | None:
        """Return last observed token usage information."""
        return self._last_usage

    def get_stream_kwargs(self) -> dict[str, Any]:
        """Return vendor-specific kwargs for astream() calls."""
        return {}
    
    def _adapt_messages_for_llama(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """Adapt messages for Llama models.
        
        Converts ToolMessage to HumanMessage with instruction to continue,
        since Llama/Qwen models don't understand ToolMessage role natively.
        """
        from langchain_core.messages import HumanMessage, ToolMessage
        
        adapted = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                # Convert ToolMessage to HumanMessage with clear instruction
                tool_content = getattr(msg, "content", "")
                adapted.append(
                    HumanMessage(
                        content=f"Tool result: {tool_content}\n\nContinue with the next step. Output ONLY the JSON tool call."
                    )
                )
            else:
                adapted.append(msg)
        
        return adapted
    
    async def ainvoke(self, messages: list[BaseMessage], **kwargs) -> AIMessage:
        """Invoke method for LangChain compatibility.
        
        This is called when bind_tools() is used (e.g. llm_with_tools.ainvoke()).
        Routes to our agenerate which has the JSON parser.
        """
        result = await self.agenerate(messages, stream=False, **kwargs)
        
        # agenerate returns either AIMessage (with tool_calls) or str
        if isinstance(result, AIMessage):
            return result
        
        # If it's a string, wrap in AIMessage
        return AIMessage(content=str(result))

