from __future__ import annotations

from . import register_model
from ._responses_base import _ResponsesFamilySpec


@register_model("gpt-5.1")
class GPT51Config(_ResponsesFamilySpec):
    pass
