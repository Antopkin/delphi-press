"""BasePrompt: Jinja2-шаблонизация промптов с structured output.

Спека: docs/07-llm-layer.md (§4).
Контракт: prompt.to_messages(**vars) → list[LLMMessage];
           prompt.parse_response(content) → BaseModel | None.
"""

from __future__ import annotations

import json
import re

from jinja2 import BaseLoader, Environment, StrictUndefined
from pydantic import BaseModel, ValidationError

from src.schemas.llm import LLMMessage, MessageRole


class PromptParseError(Exception):
    """Ошибка парсинга ответа LLM."""

    def __init__(self, message: str, raw_content: str) -> None:
        super().__init__(message)
        self.raw_content = raw_content


class BasePrompt:
    """Базовый класс для LLM-промптов с Jinja2-шаблонизацией."""

    system_template: str = ""
    user_template: str = ""
    output_schema: type[BaseModel] | None = None

    def __init__(self) -> None:
        self._env = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_system(self, **variables: object) -> str:
        """Рендерить system prompt."""
        template = self._env.from_string(self.system_template)
        return template.render(**variables).strip()

    def render_user(self, **variables: object) -> str:
        """Рендерить user prompt."""
        template = self._env.from_string(self.user_template)
        return template.render(**variables).strip()

    def to_messages(self, **variables: object) -> list[LLMMessage]:
        """Сформировать полный диалог (system + user)."""
        messages: list[LLMMessage] = []
        system = self.render_system(**variables)
        if system:
            messages.append(LLMMessage(role=MessageRole.SYSTEM, content=system))
        user = self.render_user(**variables)
        if user:
            messages.append(LLMMessage(role=MessageRole.USER, content=user))
        return messages

    def render_output_schema_instruction(self) -> str:
        """Генерировать JSON Schema инструкцию для structured output."""
        if self.output_schema is None:
            return ""
        schema = self.output_schema.model_json_schema()
        # Build a concrete example so weaker models don't confuse Field descriptions with keys
        example = {}
        for name, prop in schema.get("properties", {}).items():
            t = prop.get("type", "string")
            if t == "integer":
                example[name] = 3
            elif t == "number":
                example[name] = 0.5
            elif t == "boolean":
                example[name] = True
            elif t == "array":
                example[name] = []
            else:
                example[name] = f"<{name}>"
        return (
            "\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"```json\n{json.dumps(schema, indent=2, ensure_ascii=False)}\n```"
            f"\n\nExample response:\n"
            f"```json\n{json.dumps(example, indent=2, ensure_ascii=False)}\n```"
        )

    def parse_response(self, content: str) -> BaseModel | None:
        """Распарсить ответ LLM в Pydantic-модель."""
        if self.output_schema is None:
            return None

        # Try raw JSON
        try:
            data = json.loads(content)
            return self.output_schema.model_validate(data)
        except json.JSONDecodeError:
            pass
        except ValidationError as e:
            raise PromptParseError(str(e), raw_content=content) from e

        # Try markdown code block (with closing ```)
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return self.output_schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                raise PromptParseError(str(e), raw_content=content) from e

        # Fallback: strip opening ```json fence (truncated response without closing ```)
        stripped = re.sub(r"^```(?:json)?\s*\n?", "", content.strip())
        if stripped != content.strip():
            stripped = re.sub(r"\n?```\s*$", "", stripped)
            try:
                data = json.loads(stripped)
                return self.output_schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError):
                pass

        raise PromptParseError(
            f"Could not parse JSON from LLM response: {content[:200]}",
            raw_content=content,
        )
