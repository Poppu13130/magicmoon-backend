from datetime import datetime, timezone
from typing import Any, Dict, Optional

import os
import replicate
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.config import settings
from core.security import verify_supabase_jwt
from core.supabase_client import get_supabase_client

MODEL_ID = "ideogram-ai/ideogram-character"

# Configure the token for the Replicate client
os.environ["REPLICATE_API_TOKEN"] = settings.REPLICATE_API_TOKEN

router = APIRouter()


# ---------- SCHEMAS ----------
class IdeogramRunIn(BaseModel):
    prompt: str
    character_reference_image: Optional[str] = None
    resolution: str = "None"
    style_type: str = "Auto"
    aspect_ratio: str = "1:1"
    rendering_speed: str = "Default"
    magic_prompt_option: str = "Auto"


class PredictionCreateIn(IdeogramRunIn):
    webhook_events: list[str] = ["completed"]


def _extract_user_id(token_payload: Dict[str, Any]) -> Optional[str]:
    """
    Pull the Supabase user identifier from the decoded JWT payload.
    """
    possible_ids = [
        token_payload.get("sub"),
        token_payload.get("user_id"),
    ]
    user_claim = token_payload.get("user")
    if isinstance(user_claim, dict):
        possible_ids.append(user_claim.get("id"))

    for candidate in possible_ids:
        if candidate:
            return str(candidate)
    return None


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


# ---------- 1) Direct call (synchronous) ----------
@router.post("/ideogram/run-direct")
async def run_ideogram_direct(
    payload: IdeogramRunIn,
    token_payload: Dict[str, Any] = Depends(verify_supabase_jwt),
):
    # Token payload is only used to ensure the caller is authenticated.
    _ = token_payload
    try:
        output = replicate.run(
            MODEL_ID,
            input={
                "prompt": payload.prompt,
                "resolution": payload.resolution,
                "style_type": payload.style_type,
                "aspect_ratio": payload.aspect_ratio,
                "rendering_speed": payload.rendering_speed,
                "magic_prompt_option": payload.magic_prompt_option,
                "character_reference_image": payload.character_reference_image,
            },
        )
        output_url = getattr(output, "url", None)
        if callable(output_url):
            output_url = output_url()
        elif output_url is None and isinstance(output, str):
            output_url = output
        return {"status": "succeeded", "output_url": output_url}
    except Exception as exc:  # pragma: no cover - replicate errors bubble up
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------- 2) Prediction creation + webhook ----------
@router.post("/ideogram/predictions")
async def create_prediction(
    payload: PredictionCreateIn,
    token_payload: Dict[str, Any] = Depends(verify_supabase_jwt),
):
    if not settings.WEBHOOK_BASE_URL:
        raise HTTPException(
            status_code=500,
            detail="WEBHOOK_BASE_URL is not configured",
        )

    try:
        prediction = replicate.predictions.create(
            model=MODEL_ID,
            input={
                "prompt": payload.prompt,
                "resolution": payload.resolution,
                "style_type": payload.style_type,
                "aspect_ratio": payload.aspect_ratio,
                "rendering_speed": payload.rendering_speed,
                "magic_prompt_option": payload.magic_prompt_option,
                "character_reference_image": payload.character_reference_image,
            },
            webhook=f"{settings.WEBHOOK_BASE_URL}/ai/webhooks/replicate",
            webhook_events_filter=payload.webhook_events,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_id = _extract_user_id(token_payload)
    supabase = get_supabase_client()
    job_record: Dict[str, Any] = {
        "prediction_id": prediction.id,
        "model": MODEL_ID,
        "prompt": payload.prompt,
        "status": prediction.status,
        "metadata": payload.model_dump(exclude={"prompt"}, exclude_none=True),
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


# ---------- 3) Poll a prediction (reads from Supabase) ----------
@router.get("/predictions/{prediction_id}")
async def get_prediction(
    prediction_id: str,
    token_payload: Dict[str, Any] = Depends(verify_supabase_jwt),
):
    supabase = get_supabase_client()
    try:
        response = (
            supabase.table("replicate_jobs")
            .select("*")
            .eq("prediction_id", prediction_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch prediction state: {exc}",
        ) from exc

    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    if not data:
        raise HTTPException(status_code=404, detail="Prediction not found")

    record = data[0]
    user_id = _extract_user_id(token_payload)
    record_user_id = record.get("user_id")
    if record_user_id and user_id and str(record_user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Not authorized")

    return record


# ---------- Webhook receiver ----------
@router.post("/webhooks/replicate")
async def replicate_webhook(request: Request):
    payload = await request.json()

    prediction_id = payload.get("id")
    status = payload.get("status")

    if not prediction_id:
        raise HTTPException(
            status_code=400,
            detail="Missing prediction id in webhook payload",
        )

    normalized_status = status or "unknown"
    update_payload: Dict[str, Any] = {
        "prediction_id": prediction_id,
        "status": normalized_status,
        "output": payload.get("output"),
        "error_message": payload.get("error"),
        "updated_at": _utc_now_iso(),
    }

    metadata_from_payload = payload.get("metadata")
    if metadata_from_payload is not None:
        update_payload["metadata"] = metadata_from_payload

    if normalized_status in {"succeeded", "failed", "canceled", "completed"}:
        update_payload["completed_at"] = update_payload["updated_at"]

    supabase = get_supabase_client()
    try:
        response = (
            supabase.table("replicate_jobs")
            .upsert(update_payload, on_conflict="prediction_id")
            .select("*")
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update replicate job: {exc}",
        ) from exc

    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")

    error = getattr(response, "error", None)
    if error:
        print(
            f"[replicate_webhook] Supabase error updating prediction {prediction_id}: {error}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Supabase update error: {error}",
        )

    print(
        f"[replicate_webhook] Updated prediction {prediction_id} "
        f"status={normalized_status} job_updated={bool(data)}"
    )

    return JSONResponse(
        {
            "ok": True,
            "prediction_id": prediction_id,
            "status": normalized_status,
            "job_updated": bool(data),
        }
    )
