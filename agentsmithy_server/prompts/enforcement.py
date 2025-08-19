from __future__ import annotations

from textwrap import dedent


def build_tool_enforcement_message() -> str:
    return dedent(
        """
        🚨 CRITICAL: USER REQUESTS CODE CHANGES — YOU MUST USE THE `patch_file` TOOL!

        Do NOT return raw code edits in your assistant content.
        You MUST call `patch_file` with:
        - file_path: exact path present in context
        - changes: array of change objects with fields:
          - line_start (1-based)
          - line_end (1-based)
          - old_content (exact current code)
          - new_content (improved code)
          - reason (short explanation)

        Example tool call (conceptual):
        name: patch_file
        arguments:
          file_path: src/example.py
          changes:
            - line_start: 1
              line_end: 2
              old_content: "def a():\n    pass"
              new_content: "def a():\n    ..."
              reason: "Add behavior"
        """
    ).strip()


