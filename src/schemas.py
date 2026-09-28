"""Shared Pydantic data contracts for the harness."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class StudyType(str, Enum):
    RCT_DOUBLE_BLIND = "rct_double_blind"
    RCT_OPEN_LABEL = "rct_open_label"
    COHORT = "cohort"
    CASE_SERIES = "case_series"
    PRECLINICAL = "preclinical"
    REGISTERED_TRIAL = "registered_trial"  # ClinicalTrials.gov entry without published results yet
    OTHER = "other"


class Arm(str, Enum):
    MITOTHERAPY = "mitotherapy"
    STANDARD_OF_CARE = "standard_of_care"
    COMBINATION = "combination"
    PLACEBO = "placebo"


class EffectDirection(str, Enum):
    IMPROVED = "improved"
    NO_EFFECT = "no_effect"
    WORSE = "worse"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SourceRecord(BaseModel):
    """A raw hit returned by a search tool, before extraction."""

    source: str  # "europe_pmc" | "clinicaltrials"
    pmid: Optional[str] = None
    doi: Optional[str] = None
    nct_id: Optional[str] = None
    title: str
    year: Optional[int] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    raw: dict = Field(default_factory=dict)


class StudyRecord(BaseModel):
    """Structured extraction of one study/trial, validated against the schema."""

    pmid: Optional[str] = None
    doi: Optional[str] = None
    nct_id: Optional[str] = None
    url: Optional[str] = None
    title: str
    year: Optional[int] = None
    disease: str
    drug: str
    target: Optional[str] = Field(default=None, description="Molecular/biological target, e.g. mtDNA, complex I")
    arm: Arm
    phase: Optional[str] = Field(default=None, description="e.g. Preclinical, I, II, III, IV, N/A")
    n: Optional[int] = Field(default=None, description="Sample size")
    study_type: StudyType
    outcome_measure: Optional[str] = None
    effect_direction: EffectDirection = EffectDirection.UNKNOWN
    effect_magnitude: Optional[str] = Field(default=None, description="Free-text effect size as reported")
    evidence_level: Optional[str] = Field(default=None, description="Assigned per skills/evidence_level_scale.md")
    notes: Optional[str] = None


class ReviewIssue(BaseModel):
    record_ref: str  # pmid/doi/nct_id of the flagged record
    issue_type: str  # "unverifiable_citation" | "number_mismatch" | "hallucinated_claim" | "other"
    severity: str  # "low" | "medium" | "high"
    detail: str


class ComparisonResult(BaseModel):
    disease: str
    mitotherapy_n_studies: int
    standard_n_studies: int
    summary: str
    stats: dict = Field(default_factory=dict)
    figure_path: Optional[str] = None


class PerspectiveScore(BaseModel):
    direction: str  # drug (+ disease) label
    disease: str
    score: float = Field(ge=0, le=100)
    rank: int
    rationale: str
    evidence_level_summary: str


class PlanStep(BaseModel):
    step: str  # search | extract | compare | score | review | visualize | report
    subagent: str
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    rationale: str


class Plan(BaseModel):
    query: str
    diseases: list[str]
    drug_classes: list[str]
    date_from: int
    steps: list[PlanStep]


class FinalReport(BaseModel):
    query: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    plan: Plan
    studies: list[StudyRecord]
    comparisons: list[ComparisonResult]
    rankings: list[PerspectiveScore]
    ranking_figure_path: Optional[str] = None
    review_issues: list[ReviewIssue]
    limitations: list[str]
    plain_summary: str = ""
    markdown: str = ""


class AgentEvent(BaseModel):
    """One entry in the delegation/tool-call log, also consumed live by the UI."""

    ts: datetime = Field(default_factory=datetime.utcnow)
    actor: str  # "orchestrator" | subagent name
    phase: str  # plan | search | extract | compare | score | review | visualize | report
    event_type: str  # "start" | "tool_call" | "skill_loaded" | "llm_call" | "end" | "issue"
    message: str
    data: dict = Field(default_factory=dict)
