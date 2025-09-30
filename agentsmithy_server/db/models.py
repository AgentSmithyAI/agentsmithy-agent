from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BaseORM(DeclarativeBase):
    pass


class ToolResultORM(BaseORM):
    __tablename__ = "tool_results"

    tool_call_id: Mapped[str] = mapped_column(String, primary_key=True)
    dialog_id: Mapped[str] = mapped_column(String, index=True)
    tool_name: Mapped[str] = mapped_column(String)
    args_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DialogSummaryORM(BaseORM):
    __tablename__ = "dialog_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dialog_id: Mapped[str] = mapped_column(String, index=True)
    cutoff_message_index: Mapped[int] = mapped_column(Integer)
    summary_text: Mapped[str] = mapped_column(Text)
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
