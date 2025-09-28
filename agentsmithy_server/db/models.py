from __future__ import annotations

from sqlalchemy import Integer, String, Text
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

    dialog_id: Mapped[str] = mapped_column(String, primary_key=True)
    summary_text: Mapped[str] = mapped_column(Text)
    summarized_count: Mapped[int] = mapped_column(Integer)
    keep_last: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[str] = mapped_column(String)


class DialogUsageORM(BaseORM):
    __tablename__ = "dialog_usage"

    dialog_id: Mapped[str] = mapped_column(String, primary_key=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[str] = mapped_column(String)
