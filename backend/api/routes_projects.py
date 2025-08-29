# api/routes_projects.py
"""
Pipewise API – Projects & Network Versions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field

from core.models import Project as ProjectModel, NetworkVersion as NetworkVersionModel  # type: ignore


router = APIRouter(tags=["projects"], prefix="")

# Request/Response DTOs (aligned to API plan)
class CreateProjectReq(BaseModel):
    name: Optional[str] = None


class CreateProjectRes(BaseModel):
    project_id: str


class AddVersionReq(BaseModel):
    code: str
    meta: Optional[Dict[str, Any]] = None


class AddVersionRes(BaseModel):
    version_id: str


class ProjectItem(BaseModel):
    id: str
    name: str
    created_at: datetime


class ProjectListRes(BaseModel):
    items: List[ProjectItem]
    total: int


class NetworkVersionGetRes(BaseModel):
    id: str
    project_id: str
    version_tag: str
    created_at: datetime
    code: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class NetworkVersionListItem(BaseModel):
    id: str
    project_id: str
    version_tag: str
    created_at: datetime


class NetworkVersionListRes(BaseModel):
    items: List[NetworkVersionListItem]
    total: int


@router.post("/projects", response_model=CreateProjectRes, status_code=200, summary="Create project")
def create_project(body: CreateProjectReq, request: Request) -> CreateProjectRes:
    storage = request.app.state.storage
    pid = str(uuid.uuid4())
    proj = ProjectModel(id=pid, name=body.name or "project", metadata={}, created_at=datetime.now(timezone.utc))
    storage.save_project(proj)
    return CreateProjectRes(project_id=pid)


@router.get("/projects", response_model=ProjectListRes, summary="List projects")
def list_projects(request: Request) -> ProjectListRes:
    storage = request.app.state.storage
    items = [
        ProjectItem(id=p.id, name=p.name, created_at=p.created_at)
        for p in storage.list_projects()
    ]
    return ProjectListRes(items=items, total=len(items))


@router.get("/projects/{project_id}", response_model=ProjectItem, summary="Get project")
def get_project(project_id: str = Path(...), request: Request = None) -> ProjectItem:
    storage = request.app.state.storage
    p = storage.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectItem(id=p.id, name=p.name, created_at=p.created_at)


@router.post(
    "/projects/{project_id}/versions",
    response_model=AddVersionRes,
    status_code=200,
    summary="Add network version",
)
def add_network_version(project_id: str, body: AddVersionReq, request: Request) -> AddVersionRes:
    storage = request.app.state.storage
    # Ensure project exists
    p = storage.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    vid = str(uuid.uuid4())
    nv = NetworkVersionModel(
        id=vid,
        project_id=project_id,
        version_tag=body.meta.get("label") if body.meta else "v1",
        created_at=datetime.now(timezone.utc),
        author=None,
        payload_ref=None,
        notes=(body.meta or {}).get("notes"),
    )
    storage.save_network_version(nv, payload={"code": body.code, "meta": body.meta or {}})
    return AddVersionRes(version_id=vid)


@router.get(
    "/projects/{project_id}/versions/{version_id}",
    response_model=NetworkVersionGetRes,
    summary="Get network version",
)
def get_network_version(project_id: str, version_id: str, request: Request) -> NetworkVersionGetRes:
    storage = request.app.state.storage
    nv = storage.get_network_version(version_id)
    if not nv or nv.project_id != project_id:
        raise HTTPException(status_code=404, detail="Version not found")
    payload = storage.load_network_payload(nv) or {}
    return NetworkVersionGetRes(
        id=nv.id,
        project_id=nv.project_id,
        version_tag=nv.version_tag,
        created_at=nv.created_at,
        code=payload.get("code", ""),
        meta=payload.get("meta", {}) or {},
    )


@router.get(
    "/projects/{project_id}/versions",
    response_model=NetworkVersionListRes,
    summary="List network versions (basic)",
)
def list_network_versions(project_id: str, request: Request) -> NetworkVersionListRes:
    # Lightweight listing via direct DB access (scaffold)
    storage = request.app.state.storage
    items: List[NetworkVersionListItem] = []
    try:
        with storage._get_conn() as conn:  # noqa: SLF001 (scaffold use)
            cur = conn.cursor()
            cur.execute(
                "SELECT id, project_id, version_tag, created_at FROM network_versions WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            rows = cur.fetchall()
            for id_, pid, tag, created in rows:
                items.append(
                    NetworkVersionListItem(
                        id=id_, project_id=pid, version_tag=tag, created_at=datetime.fromisoformat(created)
                    )
                )
    except Exception:
        pass
    return NetworkVersionListRes(items=items, total=len(items))