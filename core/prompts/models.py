from pydantic import BaseModel, ConfigDict


class PromptTemplate(BaseModel):
    """System-промпт аналитика + user-шаблон с $placeholders (из <name>.yaml)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system: str
    user: str
