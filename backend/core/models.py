# core/models.py
"""
Pydantic models and enums for Pipewise backend core.

Contains domain models used throughout the backend:
- Project, NetworkVersion, AnalysisRun
- KPI, Issue, Suggestion, ModifyAction
- ToolSpec, ChatMessage
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class StatusEnum(str, Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class KpiType(str, Enum):
    PRESSURE = "pressure"
    FLOW = "flow"
    TEMPERATURE = "temperature"
    LEAK_RISK = "leak_risk"
    CUSTOM = "custom"


class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SuggestionType(str, Enum):
    CONFIG = "config"
    REPAIR = "repair"
    OPERATIONAL = "operational"
    MODEL = "model"
    OTHER = "other"


class ToolCategory(str, Enum):
    ANALYSIS = "analysis"
    SIMULATION = "simulation"
    DATA = "data"
    TRANSFORM = "transform"
    UTILITY = "utility"


class Project(BaseModel):
    id: str = Field(..., description="Unique project identifier")
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NetworkVersion(BaseModel):
    id: str
    project_id: str
    version_tag: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    author: Optional[str] = None
    payload_ref: Optional[str] = Field(
        None, description="Reference to stored network (file path, object store key, etc.)"
    )
    notes: Optional[str] = None


class Kpi(BaseModel):
    id: str
    run_id: str
    name: str
    type: KpiType
    value: float
    unit: Optional[str] = None
    status: StatusEnum = StatusEnum.UNKNOWN
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[Dict[str, Any]] = None


class Issue(BaseModel):
    id: str
    run_id: str
    title: str
    description: Optional[str] = None
    severity: IssueSeverity = IssueSeverity.MEDIUM
    status: StatusEnum = StatusEnum.WARN
    node_refs: Optional[List[str]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    extra: Optional[Dict[str, Any]] = None


class Suggestion(BaseModel):
    id: str
    issue_id: Optional[str] = None
    run_id: Optional[str] = None
    suggestion_type: SuggestionType = SuggestionType.OTHER
    title: str
    description: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    applied: bool = False
    action_ref: Optional[str] = None


class ModifyAction(BaseModel):
    id: str
    run_id: str
    title: str
    description: Optional[str] = None
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Instruction for change (e.g., {'set_pressure_limit': {'node': 'n1', 'value': 5.0}})"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    executed: bool = False
    execution_log: Optional[str] = None


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisRun(BaseModel):
    id: str
    project_id: str
    network_version_id: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: AnalysisStatus = AnalysisStatus.PENDING
    executor: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    kpis: List[Kpi] = Field(default_factory=list)
    issues: List[Issue] = Field(default_factory=list)
    suggestions: List[Suggestion] = Field(default_factory=list)
    logs: Optional[str] = None


class ToolSpec(BaseModel):
    id: str
    name: str
    category: ToolCategory = ToolCategory.UTILITY
    description: Optional[str] = None
    exec_command: Optional[List[str]] = None
    version: Optional[str] = None
    author: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    safe_to_run: bool = True


class ChatRole(str, Enum):
    SYSTEM = "system"
    ASSISTANT = "assistant"
    USER = "user"
    AGENT = "agent"


class ChatMessage(BaseModel):
    id: Optional[str] = None
    role: ChatRole
    content: str
    meta: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


__all__ = [
    "Project",
    "NetworkVersion",
    "AnalysisRun",
    "Kpi",
    "Issue",
    "Suggestion",
    "ModifyAction",
    "ToolSpec",
    "ChatMessage",
    "StatusEnum",
    "KpiType",
    "IssueSeverity",
    "SuggestionType",
    "AnalysisStatus",
    "ToolCategory",
]