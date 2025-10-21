# backend/api/routes_memory.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["memory"], prefix="")

# Lessons
class LessonItem(BaseModel):
    title: str
    body: str
    tags: List[str] = Field(default_factory=list)
    weight: float

class LessonListRes(BaseModel):
    items: List[LessonItem]
    total: int

@router.get("/memory/lessons", response_model=LessonListRes, summary="List top lessons (global+project)")
def list_lessons(project_id: Optional[str] = None, top_k: int = 10, request: Request = None) -> LessonListRes:
    mem = request.app.state.memory
    rows = mem.list_top_lessons(project_id, top_k=top_k)
    items = [LessonItem(**r) for r in rows]
    return LessonListRes(items=items, total=len(items))

# Messages (episodic trace)
class MessageItem(BaseModel):
    id: int
    project_id: Optional[str]
    run_id: Optional[str]
    role: str
    content: str
    tool_name: Optional[str] = None
    created_at: str

class MessagesRes(BaseModel):
    items: List[MessageItem]
    total: int

@router.get("/memory/messages", response_model=MessagesRes, summary="List recent messages (global+project)")
def list_messages(project_id: Optional[str] = None, limit: int = 50, request: Request = None) -> MessagesRes:
    mem = request.app.state.memory
    pid = project_id or "GLOBAL"
    items: List[MessageItem] = []
    with mem._conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, project_id, run_id, role, content, tool_name, created_at
            FROM memory_messages
            WHERE project_id IN (?, 'GLOBAL')
            ORDER BY datetime(created_at) DESC
            LIMIT ?
        """, (pid, limit))
        for row in cur.fetchall():
            items.append(MessageItem(
                id=row[0], project_id=row[1], run_id=row[2], role=row[3],
                content=row[4], tool_name=row[5], created_at=row[6]
            ))
    return MessagesRes(items=items, total=len(items))

# Run scores (learning metric)
class RunScoreItem(BaseModel):
    run_id: str
    project_id: Optional[str]
    score: float
    created_at: str

class RunScoresRes(BaseModel):
    items: List[RunScoreItem]
    total: int
    best: Optional[float] = None
    last: Optional[float] = None

@router.get("/memory/run-scores", response_model=RunScoresRes, summary="List run scores (global+project)")
def list_run_scores(project_id: Optional[str] = None, limit: int = 100, request: Request = None) -> RunScoresRes:
    mem = request.app.state.memory
    pid = project_id or "GLOBAL"
    items: List[RunScoreItem] = []
    best = mem.get_best_score(project_id)
    last = mem.get_last_score(project_id)
    with mem._conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT run_id, project_id, score, created_at
            FROM run_scores
            WHERE project_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
        """, (pid, limit))
        for row in cur.fetchall():
            items.append(RunScoreItem(run_id=row[0], project_id=row[1], score=float(row[2]), created_at=row[3]))
    return RunScoresRes(items=items, total=len(items), best=best, last=last)

# Tool stats (preferences)
class ToolStatItem(BaseModel):
    tool_name: str
    calls: int
    avg_delta: float
    last_used: Optional[str] = None

class ToolStatsRes(BaseModel):
    items: List[ToolStatItem]
    total: int

@router.get("/memory/tool-stats", response_model=ToolStatsRes, summary="List tool stats (global+project)")
def list_tool_stats(project_id: Optional[str] = None, top_k: int = 20, request: Request = None) -> ToolStatsRes:
    mem = request.app.state.memory
    pid = project_id or "GLOBAL"
    items: List[ToolStatItem] = []
    with mem._conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT tool_name, calls, avg_delta, last_used
            FROM tool_stats
            WHERE project_id IN (?, 'GLOBAL')
            ORDER BY avg_delta ASC, calls DESC
            LIMIT ?
        """, (pid, top_k))
        for row in cur.fetchall():
            items.append(ToolStatItem(tool_name=row[0], calls=int(row[1]), avg_delta=float(row[2]), last_used=row[3]))
    return ToolStatsRes(items=items, total=len(items))