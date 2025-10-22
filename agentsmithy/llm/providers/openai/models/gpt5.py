from __future__ import annotations

from . import register_model
from ._responses_base import _ResponsesFamilySpec


@register_model("gpt-5")
class GPT5Config(_ResponsesFamilySpec):
    pass
