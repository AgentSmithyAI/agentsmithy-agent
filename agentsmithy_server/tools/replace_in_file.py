from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentsmithy_server.services.versioning import VersioningTracker

from .base_tool import BaseTool


class ReplaceArgs(BaseModel):
    path: str = Field(..., description="Path to file to modify")
    diff: str = Field(
        ...,
        description="One or more SEARCH/REPLACE blocks as specified by Cline format",
    )


class ReplaceInFileTool(BaseTool):  # type: ignore[override]
    name: str = "replace_in_file"
    description: str = "Apply targeted edits to a file using SEARCH/REPLACE blocks."
    args_schema: type[BaseModel] | dict[str, Any] | None = ReplaceArgs

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:
        file_path = Path(kwargs["path"]).resolve()
        diff_text: str = kwargs["diff"]
        tracker = VersioningTracker(os.getcwd())
        tracker.ensure_repo()
        tracker.start_edit([str(file_path)])

        try:
            if diff_text.lstrip().startswith("*** Begin Patch"):
                new_text = _apply_unified_patch_to_file(diff_text, file_path)
            else:
                new_text = _apply_search_replace_blocks(diff_text, file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(new_text, encoding="utf-8")
        except Exception:
            tracker.abort_edit()
            raise
        else:
            tracker.finalize_edit()
            tracker.create_checkpoint(f"replace_in_file: {str(file_path)}")

        if self._sse_callback is not None:
            await self.emit_event({"type": "file_edit", "file": str(file_path)})

        return {"type": "replace_file_result", "path": str(file_path)}


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


def _apply_unified_patch_to_file(patch: str, file_path: Path) -> str:
    original = file_path.read_text(encoding="utf-8")
    orig_lines = original.splitlines(keepends=True)

    file_block_re = re.compile(r"\*\*\*\s+Update File:\s*(?P<path>.+)")
    lines = patch.splitlines()
    apply_block = False
    hunk_lines: list[str] = []
    for line in lines:
        m = file_block_re.match(line)
        if m:
            p = m.group("path").strip()
            apply_block = (Path(p).resolve() == file_path.resolve())
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
        m = re.match(r"@@\s*-([0-9]+)(?:,([0-9]+))?\s*\+([0-9]+)(?:,([0-9]+))?\s*@@", line)
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
