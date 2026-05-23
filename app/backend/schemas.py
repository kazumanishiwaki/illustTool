from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class StyleSummary(BaseModel):
    id: str
    labelJa: str
    styleFamilyJa: str = ""
    referenceImages: list[str] = Field(default_factory=list)
    previewImage: str = ""
    styleDifferentiator: str = ""
    visualFingerprint: dict[str, Any] = Field(default_factory=dict)


class StyleDetail(BaseModel):
    id: str
    labelJa: str
    styleFamilyJa: str = ""
    referenceGlob: str = ""
    referenceImages: list[str] = Field(default_factory=list)
    previewImage: str = ""
    styleDifferentiator: str = ""
    visualFingerprint: dict[str, str] = Field(default_factory=dict)
    visualFingerprintJa: dict[str, str] = Field(default_factory=dict)
    promptFragments: list[str] = Field(default_factory=list)
    promptFragmentsJa: list[str] = Field(default_factory=list)
    negativeFragments: list[str] = Field(default_factory=list)
    negativeFragmentsJa: list[str] = Field(default_factory=list)
    improvementRules: dict[str, str] = Field(default_factory=dict)
    improvementRulesJa: dict[str, str] = Field(default_factory=dict)
    styleScoringWeights: dict[str, int] = Field(default_factory=dict)


class StyleUpdate(BaseModel):
    labelJa: Optional[str] = None
    visualFingerprint: Optional[dict[str, str]] = None
    visualFingerprintJa: Optional[dict[str, str]] = None
    promptFragments: Optional[list[str]] = None
    promptFragmentsJa: Optional[list[str]] = None
    negativeFragments: Optional[list[str]] = None
    negativeFragmentsJa: Optional[list[str]] = None
    improvementRules: Optional[dict[str, str]] = None
    improvementRulesJa: Optional[dict[str, str]] = None


class ComposeRequest(BaseModel):
    styleId: str
    subject: str
    requiredElements: list[str] = Field(default_factory=list)
    avoidElements: list[str] = Field(default_factory=list)
    useCase: str = ""
    format: str = ""
    tone: str = ""


class VariantPrompt(BaseModel):
    label: str
    focus: str
    positive: str
    negative: str


class ComposeResult(BaseModel):
    styleId: str
    positive: str
    negative: str
    variants: list[VariantPrompt]


class CommandResult(BaseModel):
    ok: bool
    returnCode: int
    command: str
    stdout: str = ""
    stderr: str = ""


class ReviewRequest(BaseModel):
    styleId: str
    image: str
    scores: list[float] = Field(min_length=6, max_length=6)
    notes: str = ""
    hardCap: Optional[float] = None
    override: Optional[float] = None


class SyncRequest(BaseModel):
    sourceDir: str = ""
