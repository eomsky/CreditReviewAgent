"""Credit review case lifecycle endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database.poc_store import (
    create_case,
    ensure_default_case,
    get_case,
    list_cases,
    list_review_versions,
    save_review_version,
    update_case_status,
)

router = APIRouter()


class CaseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    company_name: str = Field(min_length=1, max_length=80)
    review_type: str = Field(default="정기심사", max_length=40)
    owner_name: str = Field(default="김심사", max_length=40)


class CaseStatusUpdate(BaseModel):
    status: str = Field(pattern="^(IN_PROGRESS|COMPLETED|ON_HOLD)$")


class ReviewVersionCreate(BaseModel):
    content: str = Field(min_length=20, max_length=100_000)


@router.get("")
def get_cases(status: str | None = None, query: str | None = Query(default=None, max_length=80)):
    if not list_cases():
        ensure_default_case()
    return {"items": list_cases(status=status, query=query)}


@router.post("", status_code=201)
def post_case(payload: CaseCreate):
    return create_case(payload.title, payload.company_name, payload.review_type, payload.owner_name)


@router.get("/{case_id}/review-versions")
def get_review_versions(case_id: str):
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="심사건을 찾을 수 없습니다.")
    return {"items": list_review_versions(case_id)}


@router.post("/{case_id}/review-versions", status_code=201)
def post_review_version(case_id: str, payload: ReviewVersionCreate):
    try:
        return save_review_version(case_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{case_id}")
def get_case_detail(case_id: str):
    item = get_case(case_id)
    if not item:
        raise HTTPException(status_code=404, detail="심사건을 찾을 수 없습니다.")
    return item


@router.patch("/{case_id}/status")
def patch_case_status(case_id: str, payload: CaseStatusUpdate):
    item = update_case_status(case_id, payload.status)
    if not item:
        raise HTTPException(status_code=404, detail="심사건을 찾을 수 없습니다.")
    return item