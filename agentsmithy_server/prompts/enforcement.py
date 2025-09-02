from __future__ import annotations

from textwrap import dedent


def build_tool_enforcement_message() -> str:
    return dedent(
        """
        🚨 CRITICAL: USER REQUESTS CODE CHANGES — YOU MUST USE THE `replace_in_file` TOOL!

        Do NOT return raw code edits in your assistant content.
        You MUST call `replace_in_file` with:
        - file: exact path present in context
        - search: exact current code to find
        - replace: new code to replace with

        Example tool call (conceptual):
        name: replace_in_file
        arguments:
          file: src/example.py
          search: "def a():\\n    pass"
          replace: "def a():\\n    ..."
        """
    ).strip()
