UNIVERSAL_SYSTEM = (
    "# Role and Objective"
    "- Serve as a highly skilled software engineer."
    "# Instructions"
    "- Utilize function-calling tools as required"
    "- After each tool call or code edit, validate the result in 1-2 lines and proceed or self-correct if validation fails."
    "- Do not display tool inputs/outputs in plain text unless providing a summary."
    "# Editing Files"
    "- Prioritize targeted edits for small changes to code or files."
    "- Perform complete rewrites only if absolutely necessary."
    "- Decompose code into smaller functions or modules to keep readability."
    "- If you don't have the exact information, use the web search tool to find it."
    "- Always keep in mind project's architecture and design patterns."
    "- If you are starting from scratch, use the web search tool to find the best practices."
    "# Rules"
    "- Respond using user's language, keep professional tone."
    "- Always use English for source code, comments, documentation, commit messages unless user specifies otherwise."
    "- Respond as short as possible keeping the meaning intact."
    "- Never assume outcomes from tool calls; always process actions step-by-step."
    "- Maintain concise, technical responses."
    "- When no code modification is required, provide direct answers without invoking tools."
)


def get_runtime_info(ide: str | None = None) -> str:
    """Get runtime environment information (OS, shell, IDE).

    Args:
        ide: IDE identifier (e.g., 'vscode', 'cursor', 'jetbrains') or None

    Returns:
        Formatted string with runtime information
    """
    from agentsmithy_server.platforms import get_os_adapter

    adapter = get_os_adapter()
    os_ctx = adapter.os_context()

    # Get OS info
    system = os_ctx.get("system", "Unknown")
    release = os_ctx.get("release", "")

    # Get shell
    shell = os_ctx.get("shell", "Unknown shell")
    if shell and "/" in shell:
        # Extract just the shell name from path
        shell = shell.split("/")[-1]
    elif shell and "\\" in shell:
        # Windows path
        shell = shell.split("\\")[-1]

    # IDE info
    ide_name = ide if ide else "unknown IDE"

    return (
        f"\n\n# Runtime Environment\n"
        f"- OS: {system} {release}\n"
        f"- Shell: {shell}\n"
        f"- IDE: {ide_name}\n"
    )


def get_universal_system_prompt(ide: str | None = None) -> str:
    """Get the complete universal system prompt with runtime information.

    Args:
        ide: IDE identifier or None

    Returns:
        Complete system prompt with runtime info
    """
    return UNIVERSAL_SYSTEM + get_runtime_info(ide)
