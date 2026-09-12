"""Versioned, data-only recipes. A manifest cannot execute arbitrary shell commands."""

from typing import Any, Literal

from pydantic import Field, model_validator

from negotiator.application.contracts import StrictModel


class InputSpec(StrictModel):
    id: str = Field(min_length=1)
    path: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    missing_reason: str | None = None

    @model_validator(mode="after")
    def complete_identity(self) -> "InputSpec":
        if self.missing_reason:
            if self.path is not None or self.sha256 is not None:
                raise ValueError("Unavailable inputs cannot also claim available file identities.")
        elif not self.path or not self.sha256:
            raise ValueError("Available inputs need a path and a SHA256 hash.")
        return self


class ExpectedResult(StrictModel):
    key: str = Field(min_length=1)
    value: float
    atol: float = Field(default=1e-12, ge=0)
    rtol: float = Field(default=0, ge=0)
    source: str = Field(min_length=1)


class EnvironmentSpec(StrictModel):
    framework: str = Field(min_length=1)
    python: str | None = None


class ReproductionSpec(StrictModel):
    schema_version: Literal[1] = 1
    paper_id: str = Field(min_length=1)
    result_id: str = Field(min_length=1)
    claim_scope: Literal["synthetic-validation", "published-method", "published-result"]
    analysis: Literal["profile-space", "paired-summary", "method-vectors"]
    inputs: list[InputSpec] = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    environment: EnvironmentSpec
    expected: list[ExpectedResult] = Field(default_factory=list)
    description: str = ""

    @model_validator(mode="after")
    def distinct_ids(self) -> "ReproductionSpec":
        for values in ([item.id for item in self.inputs], [item.key for item in self.expected]):
            if len(set(values)) != len(values):
                raise ValueError("Input IDs and expected-result keys must be unique.")
        return self
