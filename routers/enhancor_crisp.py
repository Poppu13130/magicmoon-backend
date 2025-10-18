from datetime import datetime, timezone
from typing import Any, Dict, Optional

import os
import replicate
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from core.config import settings
from core.security import verify_supabase_jwt
from core.supabase_client import get_supabase_client
from routers.replicate_ai import (
    _extract_user_id,
    _fetch_folder_info,
    _ltree_to_path,
    _normalize_folder_path,
    _resolve_folder_id,
)

MODEL_ID = "recraft-ai/recraft-crisp-upscale"

if settings.REPLICATE_API_TOKEN:
    os.environ["REPLICATE_API_TOKEN"] = settings.REPLICATE_API_TOKEN

router = APIRouter()


class CrispPredictionCreate(BaseModel):
    image_url: HttpUrl
    folder_id: Optional[str] = None
    folder_path: Optional[str] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_metadata(
    payload: CrispPredictionCreate,
    resolved_folder_id: Optional[str],
    resolved_folder_path: Optional[str],
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "processor": "enhancor-crisp",
        "image_url": str(payload.image_url),
        "folder_path": resolved_folder_path,
    }
    if payload.folder_id:
        metadata["requested_folder_id"] = payload.folder_id
    if payload.folder_path:
        metadata["requested_folder_path"] = _normalize_folder_path(payload.folder_path)
    if resolved_folder_id:
        metadata["resolved_folder_id"] = resolved_folder_id
    return metadata


@router.post("/enhancor-crisp/predictions")
async def create_crisp_prediction(
    payload: CrispPredictionCreate,
    token_payload: dict = Depends(verify_supabase_jwt),
):
    if payload.folder_id and payload.folder_path:
        raise HTTPException(
            status_code=400,
            detail="Provide either folder_id or folder_path, not both.",
        )

    if not settings.WEBHOOK_BASE_URL:
        raise HTTPException(
            status_code=500,
            detail="WEBHOOK_BASE_URL is not configured",
        )

    user_id = _extract_user_id(token_payload)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unable to resolve user identity")

    supabase = get_supabase_client()
    normalized_folder_path = _normalize_folder_path(payload.folder_path)

    resolved_folder_id: Optional[str] = None
    resolved_folder_path: Optional[str] = normalized_folder_path

    if normalized_folder_path:
        resolved_folder_id = _resolve_folder_id(
            supabase,
            user_id,
            None,
            normalized_folder_path,
        )
    elif payload.folder_id:
        resolved_folder_id = _resolve_folder_id(
            supabase,
            user_id,
            payload.folder_id,
            None,
        )
        if resolved_folder_id:
            folder_info = _fetch_folder_info(supabase, resolved_folder_id, user_id)
            resolved_folder_path = _ltree_to_path(
                folder_info.get("path") if folder_info else None  # type: ignore[union-attr]
            )

    try:
        prediction = replicate.predictions.create(
            model=MODEL_ID,
            input={
                "image": str(payload.image_url),
            },
            webhook=f"{settings.WEBHOOK_BASE_URL}/ai/webhooks/replicate",
            webhook_events_filter=["completed"],
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_record: Dict[str, Any] = {
        "prediction_id": prediction.id,
        "model": MODEL_ID,
        "prompt": None,
        "status": prediction.status,
        "metadata": _build_metadata(payload, resolved_folder_id, resolved_folder_path),
        "updated_at": _utc_now_iso(),
    }
    if user_id:
        job_record["user_id"] = user_id

    try:
        supabase.table("replicate_jobs").insert(job_record).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to persist replicate job: {exc}",
        ) from exc

    return {
        "prediction_id": prediction.id,
        "status": prediction.status,
    }
