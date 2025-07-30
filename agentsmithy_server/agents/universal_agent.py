"""Universal agent that handles all types of requests."""

import re
import difflib
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from agentsmithy_server.agents.base_agent import BaseAgent
from agentsmithy_server.utils.logger import agent_logger


class UniversalAgent(BaseAgent):
    """Universal agent that handles all coding tasks."""

    def get_default_system_prompt(self) -> str:
        return """You are an expert coding assistant. You can explain code, write new code, refactor, fix bugs, and review code.

**CRITICAL RULE: If you see "Selected Code:" or "Current File:" in context, AND user wants ANY changes - YOU MUST USE EDIT BLOCKS!**

**ALWAYS use edit blocks when user says:**
- "refactor" / "improve" / "optimize" / "clean up" / "simplify" 
- "fix" / "debug" / "resolve" / "correct"
- "rename" / "change" / "update" / "modify" / "rewrite"
- "add" (documentation, types, error handling, etc.)
- "remove" / "delete" / "extract" / "split"
- ANY request to change existing code in ANY way

**MANDATORY edit blocks if context contains:**
1. "Selected Code:" section (user highlighted something)
2. "Current File:" section (user has file open)  
3. User mentions file paths or line numbers
4. User references existing functions/classes/variables

**Edit block format (MANDATORY for file changes):**
```edit
file: path/to/file.py
action: edit
line_start: 10
line_end: 15
old_content: |
  def old_function():
      return "old"
new_content: |
  def improved_function():
      \"\"\"Better function with documentation.\"\"\"
      return "improved"
reason: Improved function naming and added documentation
```

**Examples:**

User: "refactor this function to be more readable"
→ MUST generate edit block with improvements

User: "fix the bug in line 23"  
→ MUST generate edit block with the fix

User: "rename getUserData to fetchUserProfile"
→ MUST generate edit block with the rename

User: "explain how this works"
→ Just explain, no edit block needed

**Guidelines:**
- Always explain your reasoning before showing the edit
- Use exact line numbers from the provided code
- Include complete functions/classes in old_content and new_content
- Be precise with indentation and formatting"""

    def get_agent_name(self) -> str:
        return "universal_agent"
        
    def _prepare_messages(self, query: str, context: Dict[str, Any]) -> List[BaseMessage]:
        """Prepare messages for LLM with enhanced edit block enforcement."""
        
        messages = [SystemMessage(content=self.system_prompt)]

        # Add context if available
        formatted_context = self.context_builder.format_context_for_prompt(context)
        if formatted_context:
            messages.append(SystemMessage(content=f"Context:\n{formatted_context}"))

        # Check if we should force edit blocks
        should_force_edits = self._should_force_edit_blocks(query, context)
        
        if should_force_edits:
            enforcement_message = SystemMessage(content="""
🚨🚨🚨 CRITICAL: USER WANTS CODE CHANGES - YOU MUST USE EDIT BLOCKS! 🚨🚨🚨

DO NOT RESPOND WITH TEXT ONLY!
YOU MUST GENERATE EDIT BLOCKS USING THIS EXACT FORMAT:

```edit
file: [exact file path from context]
action: edit  
line_start: [number]
line_end: [number]
old_content: |
  [current code exactly as shown]
new_content: |
  [improved code]
reason: [brief explanation]
```

EXAMPLE RESPONSE FORMAT:
"I'll improve this code:

```edit
file: src/example.py
action: edit
line_start: 1  
line_end: 2
old_content: |
  def old_function():
      return 'old'
new_content: |
  def improved_function():
      \"\"\"Better function.\"\"\"
      return 'improved'
reason: Added documentation and better naming
```

The function is now improved."

YOU MUST INCLUDE EDIT BLOCKS OR YOUR RESPONSE IS INVALID!
""")
            messages.append(enforcement_message)

        # Add user query
        messages.append(HumanMessage(content=query))

        return messages
        
    def _should_force_edit_blocks(self, query: str, context: Dict[str, Any]) -> bool:
        """Determine if we should force edit blocks based on query and context."""
        # Force if user has selected code or current file
        current_file = context.get("current_file") or {}
        has_selection = bool(
            current_file.get("selection") or
            current_file.get("content")
        )
        
        # Keywords that suggest modification
        modification_keywords = [
            "refactor", "improve", "optimize", "fix", "debug", "change", 
            "update", "modify", "rename", "add", "remove", "rewrite",
            "clean", "simplify", "enhance", "correct", "resolve"
        ]
        
        query_lower = query.lower()
        wants_modification = any(keyword in query_lower for keyword in modification_keywords)
        
        result = has_selection and wants_modification
        
        if result:
            agent_logger.info("Forcing edit blocks", query_contains=query_lower[:50], has_selection=has_selection)
        
        return result

    def _parse_edit_blocks(self, content: str) -> List[Dict[str, Any]]:
        """Parse edit blocks from agent response."""
        edit_blocks = []
        
        # Find all edit blocks
        pattern = r'```edit\n(.*?)\n```'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            edit_data = {}
            lines = match.strip().split('\n')
            
            current_section = None
            content_lines = []
            
            for line in lines:
                if line.startswith('file:'):
                    edit_data['file'] = line.split(':', 1)[1].strip()
                elif line.startswith('action:'):
                    edit_data['action'] = line.split(':', 1)[1].strip()
                elif line.startswith('line_start:'):
                    edit_data['line_start'] = int(line.split(':', 1)[1].strip())
                elif line.startswith('line_end:'):
                    edit_data['line_end'] = int(line.split(':', 1)[1].strip())
                elif line.startswith('reason:'):
                    edit_data['reason'] = line.split(':', 1)[1].strip()
                elif line.startswith('old_content:'):
                    current_section = 'old_content'
                    content_lines = []
                    if '|' in line:
                        continue  # Skip the | marker
                elif line.startswith('new_content:'):
                    if current_section == 'old_content':
                        edit_data['old_content'] = '\n'.join(content_lines)
                    current_section = 'new_content'
                    content_lines = []
                    if '|' in line:
                        continue  # Skip the | marker
                elif current_section:
                    content_lines.append(line)
            
            # Add the last section
            if current_section == 'new_content':
                edit_data['new_content'] = '\n'.join(content_lines)
            elif current_section == 'old_content':
                edit_data['old_content'] = '\n'.join(content_lines)
                
            if edit_data.get('file'):
                edit_blocks.append(edit_data)
                
        return edit_blocks

    def _generate_diff(self, old_content: str, new_content: str, filename: str) -> str:
        """Generate unified diff between old and new content."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=''
        )
        
        return ''.join(diff)

    async def process(
        self, query: str, context: Optional[Dict[str, Any]] = None, stream: bool = False
    ) -> Dict[str, Any]:
        """Process query and return response with file operations if needed."""
        
        if stream:
            # For streaming, handle it manually without calling super()
            # Build context
            full_context = await self.context_builder.build_context(query, context)
            
            # Prepare messages
            messages = self._prepare_messages(query, full_context)
            
            # Get streaming response directly
            response_stream = await self.llm_provider.agenerate(messages, stream=True)
            
            return {
                "agent": self.get_agent_name(),
                "response": self._stream_with_edits(response_stream),
                "context": full_context,
            }
        else:
            # Get the standard response from base agent
            result = await super().process(query, context, stream)
            # For non-streaming, parse edits and create structured response
            response_text = result["response"]
            edit_blocks = self._parse_edit_blocks(response_text)
            
            if edit_blocks:
                agent_logger.info("Edit blocks found", count=len(edit_blocks), files=[e.get('file') for e in edit_blocks])
            
            if edit_blocks:
                # Create structured response with file operations
                file_operations = []
                explanation = response_text
                
                for edit in edit_blocks:
                    if edit.get("action") == "edit":
                        diff = self._generate_diff(
                            edit.get("old_content", ""),
                            edit.get("new_content", ""),
                            edit["file"]
                        )
                        
                        file_operations.append({
                            "type": "edit",
                            "file": edit["file"],
                            "diff": diff,
                            "line_start": edit.get("line_start"),
                            "line_end": edit.get("line_end"),
                            "reason": edit.get("reason", "Code improvement")
                        })
                        
                        # Remove edit blocks from explanation
                        explanation = re.sub(r'```edit\n.*?\n```', '', explanation, flags=re.DOTALL)
                
                return {
                    "agent": self.get_agent_name(),
                    "response": {
                        "explanation": explanation.strip(),
                        "file_operations": file_operations
                    },
                    "context": result["context"],
                }
            else:
                # No file operations, return as usual
                return result

    async def _stream_with_edits(self, response_stream):
        """Stream response while parsing for edit blocks."""
        buffer = ""
        
        async for chunk in response_stream:
            buffer += chunk
            
            # Check if we have complete edit blocks
            if "```edit" in buffer and "```" in buffer.split("```edit")[1:][0] if "```edit" in buffer else False:
                # We have a complete edit block, process it
                parts = buffer.split("```edit")
                
                # Yield the text before edit block
                if parts[0].strip():
                    yield {"content": parts[0].strip()}
                
                # Process edit blocks
                for i in range(1, len(parts)):
                    if "```" in parts[i]:
                        edit_content, remaining = parts[i].split("```", 1)
                        edit_data = self._parse_single_edit("```edit\n" + edit_content + "\n```")
                        
                        if edit_data:
                            # Generate diff and send as structured event
                            diff = self._generate_diff(
                                edit_data.get("old_content", ""),
                                edit_data.get("new_content", ""),
                                edit_data["file"]
                            )
                            
                            yield {
                                "type": "diff",
                                "file": edit_data["file"],
                                "diff": diff,
                                "line_start": edit_data.get("line_start"),
                                "line_end": edit_data.get("line_end"),
                                "reason": edit_data.get("reason", "Code improvement")
                            }
                        
                        buffer = remaining
                    else:
                        # Incomplete edit block, keep in buffer
                        buffer = "```edit" + parts[i]
                        break
            else:
                # No complete edit blocks, yield as regular content
                if not ("```edit" in buffer and buffer.count("```") == 1):
                    yield {"content": chunk}

    def _parse_single_edit(self, edit_block: str) -> Optional[Dict[str, Any]]:
        """Parse a single edit block."""
        edits = self._parse_edit_blocks(edit_block)
        return edits[0] if edits else None 