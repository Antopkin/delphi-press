---
paths:
  - "src/schemas/**/*.py"
  - "src/**/*.py"
---
# Pydantic v2 Schemas

- Все модели наследуют `BaseModel` (Pydantic v2, не v1).
- Валидаторы: `@field_validator("field")` + `@classmethod`. НЕ `@validator`.
- ConfigDict: `model_config = ConfigDict(from_attributes=True)`. НЕ `class Config`.
- Обязательные поля: `Field(...)` с `description`. Опциональные: `Field(default=...)`.
- Иммутабельные результаты: `@dataclass(frozen=True)` или `model_config = ConfigDict(frozen=True)`.
- JSON парсинг: `Model.model_validate_json(text)`. НЕ `Model.parse_raw()`.
- Строковые enum: `StrEnum`, не `str, Enum`.
