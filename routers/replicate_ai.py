from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import os
import replicate
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from urllib.parse import urlparse

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
    folder_id: Optional[str] = None
    folder_path: Optional[str] = None


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


def _response_data(response: Any) -> Optional[List[Dict[str, Any]]]:
    """Normalize supabase responses to a list of dicts or None."""
    if response is None:
        return None
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return data


def _resolve_folder_id(
    supabase: Any,
    user_id: Optional[str],
    folder_id: Optional[str],
    folder_path: Optional[str],
) -> Optional[str]:
    """Validate folder information and return a folder id when possible."""
    if not user_id:
        return folder_id

    if folder_id:
        try:
            response = (
                supabase.table("folders")
                .select("id")
                .eq("id", folder_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # pragma: no cover - Supabase connectivity
            raise HTTPException(
                status_code=500,
                detail=f"Unable to validate folder_id: {exc}",
            ) from exc

        data = _response_data(response)
        if not data:
            raise HTTPException(status_code=404, detail="Folder not found for this user")
        return data[0]["id"]

    if folder_path:
        try:
            response = (
                supabase.table("folder_tree")
                .select("id")
                .eq("user_id", user_id)
                .eq("full_path", folder_path)
                .limit(1)
                .execute()
            )
            data = _response_data(response)
            if data:
                return data[0]["id"]
        except Exception as exc:  # pragma: no cover
            print(f"[replicate] Unable to resolve folder_path '{folder_path}': {exc}")
            return None

    return None


def _extract_output_urls(output: Any) -> List[str]:
    """Extract HTTP URLs from arbitrary Replicate output structures."""
    urls: List[str] = []

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            candidate = value.strip().strip('"')
            if candidate.startswith("http"):
                urls.append(candidate)
        elif isinstance(value, list):
            for item in value:
                _walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                _walk(item)

    _walk(output)
    # Deduplicate while keeping order
    seen = set()
    deduped: List[str] = []
    for url in urls:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
    return deduped


def _build_asset_fileinfo(prediction_id: str, index: int, url: str) -> Dict[str, str]:
    """Return filename and pseudo path for the asset stored in DB."""
    parsed = urlparse(url)
    base = parsed.path.rsplit("/", 1)[-1] if parsed.path else ""
    name, ext = os.path.splitext(base)
    if not ext:
        ext = ".png"
    filename = f"{prediction_id}_{index}{ext}"
    pseudo_path = f"replicate/{prediction_id}/{filename}"
    return {"filename": filename, "path": pseudo_path}


def _store_assets_for_prediction(
    supabase: Any,
    job: Dict[str, Any],
    prediction_id: str,
    urls: List[str],
) -> None:
    """Persist Replicate output URLs into the assets table for gallery usage."""
    if not urls:
        return

    user_id = job.get("user_id")
    if not user_id:
        print(
            f"[replicate_webhook] Missing user_id on job {job.get('id')} – skipping asset storage"
        )
        return

    metadata = job.get("metadata") or {}
    folder_id = metadata.get("resolved_folder_id") or metadata.get("folder_id")
    folder_path = metadata.get("folder_path")

    if not folder_id and folder_path:
        folder_id = _resolve_folder_id(supabase, user_id, None, folder_path)

    try:
        existing_resp = (
            supabase.table("assets")
            .select("id, metadata")
            .eq("source_task_id", job["id"])
            .execute()
        )
    except Exception as exc:  # pragma: no cover
        print(
            f"[replicate_webhook] Unable to read existing assets for prediction {prediction_id}: {exc}"
        )
        existing_resp = None

    existing_data = _response_data(existing_resp) or []
    existing_urls = {
        (item.get("metadata") or {}).get("external_url") for item in existing_data
    }

    new_records: List[Dict[str, Any]] = []
    for index, url in enumerate(urls):
        cleaned_url = url.strip()
        if not cleaned_url or cleaned_url in existing_urls:
            continue
        fileinfo = _build_asset_fileinfo(prediction_id, index, cleaned_url)
        asset_metadata = {
            "source": "replicate",
            "prediction_id": prediction_id,
            "external_url": cleaned_url,
            "prompt": job.get("prompt"),
            "folder_path": folder_path,
        }
        record: Dict[str, Any] = {
            "user_id": user_id,
            "type": "image",
            "path": fileinfo["path"],
            "filename": fileinfo["filename"],
            "status": "ready",
            "source_task_id": job.get("id"),
            "metadata": asset_metadata,
        }
        if folder_id:
            record["folder_id"] = folder_id
        new_records.append(record)

    if not new_records:
        return

    try:
        supabase.table("assets").insert(new_records).execute()
        print(
            f"[replicate_webhook] Inserted {len(new_records)} asset(s) for prediction {prediction_id}"
        )
    except Exception as exc:  # pragma: no cover
        print(
            f"[replicate_webhook] Failed to insert assets for prediction {prediction_id}: {exc}"
        )


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
            .update(update_payload)
            .eq("prediction_id", prediction_id)
            .execute()
        )
    except Exception as exc:
        print(
            f"[replicate_webhook] Failed to update prediction {prediction_id}: {exc}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update replicate job: {exc}",
        ) from exc

    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")

    if not data:
        print(
            f"[replicate_webhook] Prediction {prediction_id} not found when updating; "
            "attempting to insert fallback record."
        )
        try:
            insert_payload = {"prediction_id": prediction_id, **update_payload}
            response = supabase.table("replicate_jobs").insert(insert_payload).execute()
            data = getattr(response, "data", None)
            if data is None and isinstance(response, dict):
                data = response.get("data")
        except Exception as exc:
            print(
                f"[replicate_webhook] Fallback insert failed for prediction {prediction_id}: {exc}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to persist replicate job: {exc}",
            ) from exc

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
