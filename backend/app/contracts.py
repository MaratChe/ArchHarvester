from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactCreate(StrictModel):
    type_id: str
    fields: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "published"] = "draft"


class ArtifactEdit(StrictModel):
    expected_revision: int = Field(ge=1)
    fields: dict[str, Any]
    status: Literal["draft", "published"] = "draft"


class ReviewRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    fields: dict[str, Any]
    status: Literal["draft", "published"] = "draft"


class TypeCreate(StrictModel):
    create_new: bool = False
    type_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    schema_: dict = Field(alias="schema")
