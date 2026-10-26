"""Versioned contracts. Selectors are never live object handles in M0."""

from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def strict_schema_version(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value


class Result(Contract):
    schema_version: Literal[1] = 1
    command: str
    status: Literal["planned", "artifact_ready", "verified", "partial", "unknown", "needs_human", "rejected", "failed"]
    reason_code: str | None = None
    verified_scopes: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def no_invented_execution_counts(self) -> Self:
        if self.status in ("unknown", "planned", "rejected"):
            for name in ("applied_count", "verified_count"):
                if self.data.get(name) is not None:
                    raise ValueError(f"{self.status} requires {name}=null")
        return self


class NoteInput(Contract):
    key: int = Field(ge=0, le=127)
    start_tick: int = Field(ge=0)
    length_tick: int = Field(gt=0)
    velocity: int = Field(ge=1, le=127)


class NotesReplaceRequest(Contract):
    operation: Literal["notes.replace"]
    project: Path
    pattern_number: int = Field(ge=1)
    channel_index: int = Field(ge=0)
    notes: list[NoteInput]

    @field_validator("project", mode="before")
    @classmethod
    def absolute_project(cls, value: Any) -> Path:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError("project must be a nonempty filesystem path")
        return Path(value).resolve()


class Plan(Contract):
    schema_version: Literal[1] = 1
    request: NotesReplaceRequest
    request_sha256: str
    source_sha256: str
    executable: Literal[False] = False
    target_resolution: Literal["unresolved_selectors"] = "unresolved_selectors"
    bound_target: None = None
    unmet_requirements: list[str]
    effects: list[str]
    requested_count: int = Field(ge=0)
    artifact_count: None = None
    applied_count: None = None
    verified_count: None = None


class Capability(Contract):
    operation: str
    implemented: bool
    availability: Literal["available", "not_implemented"]
    verification_level: Literal["source_only", "offline_fixture", "live", "persistence", "audio"]
    backend: str | None
    profile: str | None = None
    requires_desktop: bool = False
    limitations: list[str] = Field(default_factory=list)
    external_evidence: list[str] = Field(default_factory=list)
    last_evidence: str | None = None
