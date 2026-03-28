"""Prompts for generator agents (Stages 7-9).

Спека: docs/06-generators.md
"""

from src.llm.prompts.generators.framing import FramingPrompt
from src.llm.prompts.generators.quality import FactualCheckPrompt, StyleCheckPrompt
from src.llm.prompts.generators.style import GeneratedHeadlineSet, StylePrompt

__all__ = [
    "FactualCheckPrompt",
    "FramingPrompt",
    "GeneratedHeadlineSet",
    "StyleCheckPrompt",
    "StylePrompt",
]
