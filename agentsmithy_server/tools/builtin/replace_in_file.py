from __future__ import annotations

import difflib
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentsmithy_server.services.versioning import VersioningTracker
from agentsmithy_server.utils.logger import agent_logger

from ..base_tool import BaseTool


class ReplaceArgs(BaseModel):
    path: str = Field(..., description="Path to file to modify")
    diff: str = Field(
        ...,
        description=(
            "Diff content in MARKER style:\n"
            "------- SEARCH\n"
            "[exact lines to find] (full lines)\n"
            "=======\n"
            "[replacement lines] (full lines)\n"
            "+++++++ REPLACE\n"
            "Rules: keep markers exactly as shown (7+ dashes/equals/pluses accepted);"
            " provide blocks in file order; empty SEARCH means replace whole file;"
            " do not include any extra text outside the blocks."
        ),
    )


class ReplaceInFileTool(BaseTool):  # type: ignore[override]
    name: str = "replace_in_file"
    description: str = (
        "Edit a file by applying a diff. Required format:\n"
        "```\n"
        "------- SEARCH\n"
        "[exact lines to find]\n"
        "=======\n"
        "[replacement lines]\n"
        "+++++++ REPLACE\n"
        "```\n"
        "Features: exact match, line-trimmed match (ignores whitespace), block anchor match (3+ lines);\n"
        "multiple blocks allowed; empty SEARCH replaces whole file; handles out-of-order edits."
    )
    args_schema: type[BaseModel] | dict[str, Any] | None = ReplaceArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        file_path = Path(kwargs["path"]).resolve()
        diff_text: str = kwargs["diff"]
        tracker = VersioningTracker(os.getcwd(), dialog_id=self._dialog_id)
        tracker.ensure_repo()
        tracker.start_edit([str(file_path)])

        checkpoint = None
        try:
            agent_logger.info("replace_in_file start", path=str(file_path))
            original_text = (
                file_path.read_text(encoding="utf-8") if file_path.exists() else ""
            )

            if diff_text.lstrip().startswith("*** Begin Patch"):
                new_text = _apply_unified_patch_to_file(diff_text, file_path)
            elif _looks_like_marker_style(diff_text):
                new_text = _apply_marker_style_blocks(diff_text, file_path)
            else:
                new_text = _apply_search_replace_blocks(diff_text, file_path)

            # Check if anything actually changed
            if new_text == original_text and file_path.exists():
                tracker.abort_edit()
                raise ValueError(
                    "No changes were made - diff pattern not found in file"
                )

            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(new_text, encoding="utf-8")
        except Exception as e:
            tracker.abort_edit()
            # Provide more context in error messages
            if isinstance(e, ValueError) and "does not match" in str(e):
                # Add file content preview to help LLM understand the issue
                preview_lines = original_text.splitlines()[:20]
                preview = "\n".join(preview_lines)
                if len(preview_lines) < len(original_text.splitlines()):
                    preview += "\n... (file continues)"

                enhanced_error = (
                    f"{str(e)}\n\n"
                    f"File preview (first 20 lines):\n"
                    f"```\n{preview}\n```\n\n"
                    f"Hint: Try using smaller, more specific SEARCH blocks or check for whitespace differences."
                )
                raise ValueError(enhanced_error) from e
            raise
        else:
            tracker.finalize_edit()
            checkpoint = tracker.create_checkpoint(f"replace_in_file: {str(file_path)}")

        diff_str: str | None = None
        if self._sse_callback is not None:
            # Build unified diff between original and new content
            unified = difflib.unified_diff(
                original_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
            )
            diff_str = "\n".join(unified)
            agent_logger.info(
                "replace_in_file emit_event",
                path=str(file_path),
                has_callback=self._sse_callback is not None,
                diff_len=len(diff_str),
            )
            await self.emit_event(
                {
                    "type": "file_edit",
                    "file": str(file_path),
                    "diff": diff_str,
                    "checkpoint": getattr(checkpoint, "commit_id", None),
                }
            )

        return {
            "type": "replace_file_result",
            "path": str(file_path),
            "diff": diff_str,
            "checkpoint": getattr(checkpoint, "commit_id", None),
        }


def _apply_search_replace_blocks(diff_text: str, file_path: Path) -> str:
    original = file_path.read_text(encoding="utf-8")
    text = original
    pattern = re.compile(
        r"<<<<<<<\s*SEARCH\n(?P<search>[\s\S]*?)\n\+{6,}\s*REPLACE\n(?P<replace>[\s\S]*?)\n>>>>>>>",
        re.MULTILINE,
    )
    replaced_any = False
    start_pos = 0
    for m in pattern.finditer(diff_text):
        search = m.group("search")
        # Normalize common regex-escaped punctuation to literal characters
        search = re.sub(r"\\([\\|().{}\[\]^$*+?])", r"\1", search)
        replace = m.group("replace")

        # Find next occurrence from current start_pos
        idx = text.find(search, start_pos)
        if idx == -1:
            raise ValueError("SEARCH block content not found in file")

        # Avoid double newlines: if the character immediately after the matched search
        # in the original text is a newline and the replacement ends with a newline,
        # replace the span including that newline.
        end_idx = idx + len(search)
        if end_idx < len(text) and text[end_idx] == "\n" and replace.endswith("\n"):
            # Replace search + one following newline
            text = text[:idx] + replace + text[end_idx + 1 :]
            start_pos = idx + len(replace)
        else:
            text = text[:idx] + replace + text[end_idx:]
            start_pos = idx + len(replace)

        replaced_any = True
    # Preserve trailing newline if replacement includes it; otherwise keep as-is
    if not replaced_any:
        return original
    return text


def _looks_like_marker_style(diff_text: str) -> bool:
    # Detect generic marker-style blocks: ------- SEARCH / ======= / +++++++ REPLACE
    # Also supports <<<<<<< SEARCH / ======= / +++++++ REPLACE
    return (
        re.search(r"^[-<]{3,}\s*SEARCH", diff_text, re.MULTILINE) is not None
        or re.search(r"^[=]{3,}$", diff_text, re.MULTILINE) is not None
        or re.search(r"^[+]{3,}\s*REPLACE", diff_text, re.MULTILINE) is not None
    )


def _block_anchor_fallback(
    original: str, search: str, start_index: int
) -> tuple[int, int] | None:
    """
    Block anchor matching strategy.
    For blocks of 3+ lines, match using first and last lines as anchors.
    """
    orig_lines = original.split("\n")
    search_lines = search.split("\n")

    # Remove trailing empty line if exists
    if search_lines and search_lines[-1] == "":
        search_lines.pop()

    # Only use for blocks of 3+ lines
    if len(search_lines) < 3:
        return None

    first_line_search = search_lines[0].strip()
    last_line_search = search_lines[-1].strip()
    search_block_size = len(search_lines)

    # Find starting line from start_index
    current = 0
    start_line = 0
    while current < start_index and start_line < len(orig_lines):
        current += len(orig_lines[start_line]) + 1
        start_line += 1

    # Look for matching start and end anchors
    for i in range(start_line, len(orig_lines) - search_block_size + 1):
        # Check if first line matches
        if orig_lines[i].strip() != first_line_search:
            continue

        # Check if last line matches at expected position
        if orig_lines[i + search_block_size - 1].strip() != last_line_search:
            continue

        # Calculate exact character positions
        start_char = sum(len(line) + 1 for line in orig_lines[:i])
        # Ensure we don't include the final newline if it doesn't exist
        if i + search_block_size >= len(orig_lines):
            # Last block - no trailing newline
            end_char = start_char + sum(
                len(line) for line in orig_lines[i : i + search_block_size]
            )
            end_char += search_block_size - 1  # Add newlines between lines
        else:
            end_char = start_char + sum(
                len(line) + 1 for line in orig_lines[i : i + search_block_size]
            )

        return (start_char, end_char)

    return None


def _trimmed_line_fallback(
    original: str, search: str, start_index: int
) -> tuple[int, int] | None:
    orig_lines = original.split("\n")
    search_lines = search.split("\n")
    if search_lines and search_lines[-1] == "":
        search_lines.pop()

    # locate starting line index from start_index
    current = 0
    start_line = 0
    while current < start_index and start_line < len(orig_lines):
        current += len(orig_lines[start_line]) + 1
        start_line += 1

    for i in range(start_line, len(orig_lines) - len(search_lines) + 1):
        match = True
        for j in range(len(search_lines)):
            if orig_lines[i + j].strip() != search_lines[j].strip():
                match = False
                break
        if match:
            # compute char indices
            start_char = sum(len(line_text) + 1 for line_text in orig_lines[:i])
            end_char = start_char + sum(
                len(line_text) + 1
                for line_text in orig_lines[i : i + len(search_lines)]
            )
            return (start_char, end_char)
    return None


def _try_fix_malformed_blocks(diff_text: str) -> str:
    """Attempt to fix common malformed block issues."""
    lines = diff_text.splitlines()
    fixed_lines = []

    for _i, line in enumerate(lines):
        # Fix common marker variations
        if re.match(r"^-{3,6}\s*SEARCH", line):
            fixed_lines.append("------- SEARCH")
        elif re.match(r"^={3,6}$", line):
            fixed_lines.append("=======")
        elif re.match(r"^\+{3,6}\s*REPLACE", line):
            fixed_lines.append("+++++++ REPLACE")
        else:
            fixed_lines.append(line)

    return "\n".join(fixed_lines)


def _apply_marker_style_blocks(diff_text: str, file_path: Path) -> str:
    # Try to fix common malformed blocks first
    fixed_diff = _try_fix_malformed_blocks(diff_text)
    if fixed_diff != diff_text:
        agent_logger.info("Fixed malformed diff blocks")
        diff_text = fixed_diff

    original = file_path.read_text(encoding="utf-8")

    # Track all replacements for out-of-order editing support
    replacements: list[dict] = []

    search_start_re = re.compile(r"^[-<]{3,}\s*SEARCH>?$")
    middle_re = re.compile(r"^[=]{3,}$")
    replace_end_re = re.compile(r"^[+>]{3,}\s*(REPLACE>?)?$")

    lines = diff_text.splitlines()
    state = "idle"
    search_buf: list[str] = []
    replace_buf: list[str] = []
    pending_search: str = ""  # For alternative format

    def apply_one(search_block: str, replace_block: str) -> None:
        # Empty SEARCH => full file replacement
        if search_block == "":
            replacements.append(
                {
                    "start": 0,
                    "end": len(original),
                    "content": replace_block,
                    "method": "full_replace",
                }
            )
            return

        # Try multiple matching strategies in order
        match_result = None
        method_used = None
        search_from = 0  # Search from beginning to support out-of-order

        # 1. Exact match
        idx = original.find(search_block, search_from)
        if idx != -1:
            match_result = (idx, idx + len(search_block))
            method_used = "exact_match"
        else:
            # 2. Trimmed line fallback
            match_result = _trimmed_line_fallback(original, search_block, search_from)
            if match_result:
                method_used = "line_trimmed"
            else:
                # 3. Block anchor fallback
                match_result = _block_anchor_fallback(
                    original, search_block, search_from
                )
                if match_result:
                    method_used = "block_anchor"

        if not match_result:
            # Extract a sample of what we were looking for
            search_preview = (
                search_block[:100] + "..." if len(search_block) > 100 else search_block
            )
            raise ValueError(
                f"The SEARCH block does not match anything in the file:\n"
                f"```\n{search_preview}\n```\n"
                f"Tried: exact match, line-trimmed match, block anchor match"
            )

        start, end = match_result
        agent_logger.debug(
            "Match found",
            method=method_used,
            start=start,
            end=end,
            search_len=len(search_block),
        )

        replacements.append(
            {
                "start": start,
                "end": end,
                "content": replace_block,
                "method": method_used,
            }
        )

    for line in lines:
        if search_start_re.match(line):
            state = "search"
            search_buf = []
            replace_buf = []
            continue
        if middle_re.match(line):
            if state != "search":
                # ignore malformed
                continue
            state = "replace"
            continue
        if replace_end_re.match(line):
            if state == "replace":
                # Normal case: ------- SEARCH ... ======= ... +++++++ REPLACE
                search_block = "\n".join(search_buf)
                # Normalize common regex-escaped punctuation to literal characters
                search_block = re.sub(r"\\([\\|().{}\[\]^$*+?])", r"\1", search_block)
                replace_block = "\n".join(replace_buf)
                # Ensure trailing newline behavior is exact: keep as-is
                apply_one(search_block, replace_block)
                state = "idle"
                search_buf = []
                replace_buf = []
                continue
            elif state == "search":
                # Alternative format: ------- SEARCH ... +++++++ REPLACE (no =======)
                # In this case, everything after +++++++ REPLACE is the replacement
                search_block = "\n".join(search_buf)
                search_block = re.sub(r"\\([\\|().{}\[\]^$*+?])", r"\1", search_block)
                pending_search = search_block
                # Start collecting replacement content from next line
                state = "replace_after_marker"
                search_buf = []
                replace_buf = []
                continue

        if state == "search":
            search_buf.append(line)
        elif state == "replace":
            replace_buf.append(line)
        elif state == "replace_after_marker":
            # Collecting replacement content after +++++++ REPLACE marker
            # Stop if we encounter a closing marker like '>>>>>>>' on its own line
            if re.match(r"^>{3,}\s*$", line):
                # finalize this replacement block
                state = "idle"
                if pending_search:
                    replace_block = "\n".join(replace_buf)
                    apply_one(pending_search, replace_block)
                    pending_search = ""
                replace_buf = []
                continue
            # Otherwise, this is the rest of the diff content
            replace_buf.append(line)

    # Handle case where diff ends in replace_after_marker state
    if state == "replace_after_marker" and pending_search:
        replace_block = "\n".join(replace_buf)
        apply_one(pending_search, replace_block)
    # Apply all replacements in order
    replacements.sort(key=lambda r: r["start"])

    result = ""
    current_pos = 0

    for replacement in replacements:
        # Check for overlapping replacements
        if replacement["start"] < current_pos:
            agent_logger.warning(
                "Overlapping replacement detected",
                start=replacement["start"],
                current_pos=current_pos,
            )
            continue

        # Add original content up to this replacement
        result += original[current_pos : replacement["start"]]
        # Add the replacement content
        result += replacement["content"]
        # Move position to after the replaced section
        current_pos = replacement["end"]

    # Add any remaining original content
    result += original[current_pos:]

    return result


def _apply_unified_patch_to_file(patch: str, file_path: Path) -> str:
    original = file_path.read_text(encoding="utf-8")
    orig_lines = original.splitlines(keepends=True)

    file_block_re = re.compile(r"\*\*\*\s+Update File:\s*(?P<path>.+)")
    lines = patch.splitlines()
    # By default, collect hunks; if specific Update File blocks are present and
    # do not match this file, we'll skip those blocks.
    apply_block = True
    hunk_lines: list[str] = []
    for line in lines:
        m = file_block_re.match(line)
        if m:
            p = m.group("path").strip()
            # Switch to only applying hunks for matching file blocks
            apply_block = Path(p).resolve() == file_path.resolve()
            continue
        if not apply_block:
            continue
        if line.startswith("@@") or line[:1] in {"+", "-", " "}:
            hunk_lines.append(line)

    if not hunk_lines:
        return original

    result: list[str] = []
    orig_idx = 0
    i = 0
    while i < len(hunk_lines):
        line = hunk_lines[i]
        if not line.startswith("@@"):
            i += 1
            continue
        m = re.match(
            r"@@\s*-([0-9]+)(?:,([0-9]+))?\s*\+([0-9]+)(?:,([0-9]+))?\s*@@", line
        )
        if not m:
            i += 1
            continue
        old_start = int(m.group(1))
        copy_upto = max(0, old_start - 1)
        result.extend(orig_lines[orig_idx:copy_upto])
        orig_idx = copy_upto
        i += 1
        while i < len(hunk_lines) and not hunk_lines[i].startswith("@@"):
            hl = hunk_lines[i]
            if hl.startswith(" "):
                if orig_idx < len(orig_lines):
                    result.append(orig_lines[orig_idx])
                    orig_idx += 1
            elif hl.startswith("-"):
                if orig_idx < len(orig_lines):
                    orig_idx += 1
            elif hl.startswith("+"):
                result.append(hl[1:] + ("\n" if not hl.endswith("\n") else ""))
            i += 1

    result.extend(orig_lines[orig_idx:])
    return "".join(result)
