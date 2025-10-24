from __future__ import annotations

import zlib

from sqlalchemy import Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class BaseORM(DeclarativeBase):
    pass


def compress_text(text: str) -> bytes:
    """Compress text using zlib for storage."""
    return zlib.compress(text.encode("utf-8"), level=6)


def decompress_text(data: bytes) -> str:
    """Decompress zlib-compressed data back to text."""
    return zlib.decompress(data).decode("utf-8")


class CompressedText(TypeDecorator):
    """SQLAlchemy type that automatically compresses text data.

    Stores data as compressed bytes in the database but presents it as
    text in Python.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Compress text before storing in database."""
        if value is None:
            return None
        # Skip if already bytes (already compressed)
        if isinstance(value, bytes):
            return value
        return compress_text(value)

    def process_result_value(self, value, dialect):
        """Decompress data when reading from database."""
        if value is None:
            return None
        return decompress_text(value)


class ToolResultORM(BaseORM):
    __tablename__ = "tool_results"

    tool_call_id: Mapped[str] = mapped_column(String, primary_key=True)
    dialog_id: Mapped[str] = mapped_column(String, index=True)
    tool_name: Mapped[str] = mapped_column(String)
    args_json: Mapped[str] = mapped_column(CompressedText)
    result_json: Mapped[str] = mapped_column(CompressedText)
    timestamp: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DialogSummaryORM(BaseORM):
    __tablename__ = "dialog_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dialog_id: Mapped[str] = mapped_column(String, index=True)
    cutoff_message_index: Mapped[int] = mapped_column(Integer)
    summary_text: Mapped[str] = mapped_column(CompressedText)
    keep_last: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String)
    summarized_count: Mapped[int] = mapped_column(Integer)
    __table_args__ = (Index("ix_summaries_dialog_created", "dialog_id", "created_at"),)


class DialogUsageORM(BaseORM):
    __tablename__ = "dialog_usage"

    dialog_id: Mapped[str] = mapped_column(String, primary_key=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[str] = mapped_column(String)


class DialogUsageEventORM(BaseORM):
    __tablename__ = "dialog_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dialog_id: Mapped[str] = mapped_column(String, index=True)
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String)

    __table_args__ = (
        Index("ix_usage_events_dialog_created", "dialog_id", "created_at"),
    )


class DialogReasoningORM(BaseORM):
    """Stores reasoning/thinking traces from LLM responses.

    Each reasoning block can be linked to a specific message in the dialog history
    via message_index, allowing reconstruction of the model's thinking process.
    """

    __tablename__ = "dialog_reasoning"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dialog_id: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(CompressedText)
    created_at: Mapped[str] = mapped_column(String)
    # Index of the message in dialog history this reasoning relates to (-1 if not yet linked)
    message_index: Mapped[int] = mapped_column(Integer, default=-1)
    # Optional: model that generated this reasoning
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("ix_reasoning_dialog_created", "dialog_id", "created_at"),
        Index("ix_reasoning_dialog_msg_idx", "dialog_id", "message_index"),
    )


class DialogFileEditORM(BaseORM):
    """Stores file edit events from tool executions.

    Captures when files are modified/created/deleted during dialog execution.
    """

    __tablename__ = "dialog_file_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dialog_id: Mapped[str] = mapped_column(String, index=True)
    file: Mapped[str] = mapped_column(String)  # File path
    diff: Mapped[str | None] = mapped_column(
        CompressedText, nullable=True
    )  # Diff content
    checkpoint: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # Git commit id
    created_at: Mapped[str] = mapped_column(String)
    message_index: Mapped[int] = mapped_column(Integer, default=-1)

    __table_args__ = (Index("ix_file_edits_dialog_created", "dialog_id", "created_at"),)


class SessionORM(BaseORM):
    """Stores session (approval branch) information for a dialog."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_name: Mapped[str] = mapped_column(String, unique=True)  # "session_1", etc.
    ref_name: Mapped[str] = mapped_column(String)  # "refs/heads/session_1"
    status: Mapped[str] = mapped_column(String)  # "active", "merged", "abandoned"
    created_at: Mapped[str] = mapped_column(String)
    closed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_commit: Mapped[str | None] = mapped_column(String, nullable=True)
    checkpoints_count: Mapped[int] = mapped_column(Integer, default=0)
    branch_exists: Mapped[bool] = mapped_column(
        Integer, default=1
    )  # SQLite uses INTEGER for BOOLEAN

    __table_args__ = (Index("ix_sessions_status", "status"),)


class DialogBranchORM(BaseORM):
    """Stores Git branch metadata for a dialog."""

    __tablename__ = "dialog_branches"

    branch_type: Mapped[str] = mapped_column(
        String, primary_key=True
    )  # "main" or "session"
    ref_name: Mapped[str] = mapped_column(String)
    head_commit: Mapped[str | None] = mapped_column(String, nullable=True)
    valid: Mapped[bool] = mapped_column(
        Integer, default=1
    )  # SQLite uses INTEGER for BOOLEAN
