"""Granite-specific ChatOpenAI wrapper that parses tool calls from content.

Granite models return tool calls in XML format within the content field:
<tool_call>
{"name": "function_name", "arguments": "{...}"}
</tool_call>

This wrapper intercepts responses and converts them to standard OpenAI format
with tool_calls array.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from langchain_openai import ChatOpenAI


class GraniteChatOpenAI(ChatOpenAI):
    """ChatOpenAI wrapper for Granite models with tool call parsing.

    Granite models use XML-style tool call syntax in content instead of
    the standard OpenAI tool_calls array. This wrapper parses that format
    and converts it to the expected structure.

    Also ensures proper system prompt for tool use activation.
    """

    def bind_tools(
        self,
        tools: Any,
        **kwargs: Any,
    ) -> Any:
        """Bind tools with Granite-specific configuration."""
        # Don't set tool_choice - let it be None/default
        # llama-cpp-python might have issues with tool_choice parameter
        return super().bind_tools(tools, **kwargs)

    def _post_process_response(self, response: Any) -> Any:
        """Post-process response to convert Granite tool calls to OpenAI format."""
        # Handle both ChatCompletion and Message objects
        if hasattr(response, "choices") and response.choices:
            # Full completion response
            for choice in response.choices:
                if hasattr(choice, "message"):
                    self._convert_message_tool_calls(choice.message)
        elif hasattr(response, "content"):
            # Direct message object
            self._convert_message_tool_calls(response)

        return response

    def _convert_message_tool_calls(self, message: Any) -> None:
        """Convert Granite <tool_call> format to OpenAI tool_calls in message."""
        if not hasattr(message, "content") or not message.content:
            return

        content = message.content
        if not isinstance(content, str) or "<tool_call>" not in content:
            return

        # Parse tool calls
        remaining, tool_calls = self._parse_granite_tool_calls(content)

        if tool_calls:
            # Update message content and add tool_calls
            message.content = remaining
            # OpenAI format uses tool_calls attribute
            if not hasattr(message, "tool_calls"):
                message.tool_calls = []
            message.tool_calls = tool_calls

    def _parse_granite_tool_calls(
        self, content: str
    ) -> tuple[str | None, list[dict[str, Any]] | None]:
        """Parse Granite's <tool_call> format from content.

        Returns:
            (remaining_content, tool_calls) where remaining_content is text
            outside tool call tags, and tool_calls is list of parsed calls
        """
        # Decode only specific HTML entities that appear in tags
        # Don't use full html.unescape as it breaks JSON escaping
        decoded_content = (
            content.replace("&lt;", "<").replace("&gt;", ">").replace("&#34;", '"')
        )

        # Find all <tool_call>...</tool_call> blocks using greedy match
        # Need to handle nested braces in JSON
        pattern = r"<tool_call>\s*(.*?)\s*</tool_call>"
        matches = re.findall(pattern, decoded_content, re.DOTALL)

        if not matches:
            return content, None

        # Parse each tool call
        tool_calls = []
        for match in matches:
            match = match.strip()
            # Try to parse as JSON
            try:
                # First pass: try direct parse
                data = json.loads(match)
            except json.JSONDecodeError:
                # Second pass: try to fix escaped newlines and quotes
                # Granite sometimes returns: {"name": "x", "arguments": "{\n  \"city\": \"Madrid\"\n}"}
                # The inner JSON is a string with real newlines
                try:
                    # Replace real newlines in the match with escaped ones
                    fixed_match = match.replace("\n", "\\n")
                    data = json.loads(fixed_match)
                except json.JSONDecodeError:
                    import logging

                    logger = logging.getLogger("agentsmithy.agents")
                    logger.warning(
                        f"Failed to parse tool call JSON, skipping: {match[:100]}"
                    )
                    continue

            # Handle arguments - can be dict or string
            args = data.get("arguments", {})
            if isinstance(args, dict):
                # Convert dict to JSON string for OpenAI format
                args_str = json.dumps(args)
            elif isinstance(args, str):
                # String argument - use as is
                args_str = args
            else:
                args_str = "{}"

            tool_call = {
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": data.get("name", ""),
                    "arguments": args_str,
                },
            }
            tool_calls.append(tool_call)

        # Remove tool call tags from decoded content
        remaining_content = re.sub(
            pattern, "", decoded_content, flags=re.DOTALL
        ).strip()

        return remaining_content or None, tool_calls if tool_calls else None

    def _generate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Override generation to post-process Granite tool calls."""
        # Log what we're sending (for debugging)
        import logging

        logger = logging.getLogger("agentsmithy.agents")
        logger.debug(
            f"Granite _generate: messages={len(messages)}, kwargs keys={list(kwargs.keys())}"
        )

        result = super()._generate(messages, stop, run_manager, **kwargs)
        return self._post_process_response(result)

    async def _agenerate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Override async generation to post-process Granite tool calls."""
        import json
        import logging
        import random

        logger = logging.getLogger("agentsmithy.agents")

        # Detailed logging
        logger.debug(
            f"Granite _agenerate: messages={len(messages)}, kwargs keys={list(kwargs.keys())}"
        )
        for i, msg in enumerate(messages):
            msg_dict = msg.dict() if hasattr(msg, "dict") else str(msg)
            logger.debug(
                f"  Message {i}: {json.dumps(msg_dict, ensure_ascii=False)[:200]}"
            )

        if "tools" in kwargs:
            logger.debug(f"  Tools count: {len(kwargs['tools'])}")
            logger.debug(
                f"  Tools: {json.dumps(kwargs['tools'], ensure_ascii=False)[:500]}"
            )

        # Try with reduced parameters to avoid llama_decode error
        # Keep only tools, remove tool_choice and other potentially problematic params
        clean_kwargs = {}
        if "tools" in kwargs:
            clean_kwargs["tools"] = kwargs["tools"]
        # Do NOT include tool_choice - it seems to break llama-cpp-python

        # WORKAROUND для llama-cpp-python KV cache bug:
        # Добавляем параметры которые могут помочь избежать конфликтов
        # 1. Random seed для каждого запроса
        clean_kwargs["seed"] = random.randint(1, 999999)
        # 2. Попробуем включить stream даже для не-streaming запросов
        # (иногда это обходит проблемы с кешем)
        # НО это может сломать LangChain, поэтому закомментировано
        # clean_kwargs['stream'] = False

        try:
            result = await super()._agenerate(
                messages, stop, run_manager, **clean_kwargs
            )
            return self._post_process_response(result)
        except Exception as e:
            logger.error(f"Granite generation failed: {e}")
            raise
