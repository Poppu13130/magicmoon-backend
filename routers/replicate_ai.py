from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import json

import httpx
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


def _normalize_folder_path(folder_path: Optional[str]) -> Optional[str]:
    """Normalize folder path strings (split on '/', remove empties)."""
    if not folder_path:
        return None
    segments = [segment.strip() for segment in folder_path.split("/") if segment.strip()]
    if not segments:
        return None
    return "/".join(segments)


def _ltree_to_path(ltree_value: Optional[str]) -> Optional[str]:
    if not ltree_value:
        return None
    return "/".join(part for part in ltree_value.split(".") if part)


def _response_data(response: Any) -> Optional[List[Dict[str, Any]]]:
    """Normalize supabase responses to a list of dicts or None."""
    if response is None:
        return None
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return data


def _ensure_folder_path(
    supabase: Any, user_id: str, folder_path: str
) -> Tuple[str, str]:
    """
    Ensure the provided slash-separated folder path exists.
    Returns (folder_id, normalized_path)
    """
    normalized = _normalize_folder_path(folder_path)
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid folder_path value")

    segments = normalized.split("/")
    current_id: Optional[str] = None
    path_parts: List[str] = []

    for segment in segments:
        path_parts.append(segment)
        ltree_value = ".".join(path_parts)

        try:
            response = (
                supabase.table("folders")
                .select("id")
                .eq("user_id", user_id)
                .eq("path", ltree_value)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Unable to check folder path '{normalized}': {exc}",
            ) from exc

        data = _response_data(response)
        if data:
            current_id = data[0]["id"]
            continue

        insert_payload = {
            "user_id": user_id,
            "name": segment,
            "parent_id": current_id,
            "path": ltree_value,
        }
        try:
            insert_response = (
                supabase.table("folders")
                .insert(insert_payload)
                .select("id")
                .execute()
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Unable to create folder '{segment}' in path '{normalized}': {exc}",
            ) from exc

        insert_data = _response_data(insert_response)
        if not insert_data:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create folder path '{normalized}'",
            )
        current_id = insert_data[0]["id"]

    if current_id is None:
        raise HTTPException(
            status_code=500, detail=f"Unable to determine folder id for '{normalized}'"
        )

    return current_id, normalized


def _fetch_folder_info(
    supabase: Any, folder_id: str, user_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    try:
        query = supabase.table("folders").select("id, user_id, path, name").eq("id", folder_id)
        if user_id:
            query = query.eq("user_id", user_id)
        response = query.limit(1).execute()
    except Exception as exc:  # pragma: no cover
        print(f"[folders] Unable to fetch folder info for id {folder_id}: {exc}")
        return None
    data = _response_data(response)
    return data[0] if data else None


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
            ensured_id, _ = _ensure_folder_path(supabase, user_id, folder_path)
            return ensured_id
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover
            print(f"[replicate] Unable to ensure folder_path '{folder_path}': {exc}")
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


def _build_asset_fileinfo(
    prediction_id: str,
    index: int,
    url: str,
    folder_path: Optional[str] = None,
) -> Dict[str, str]:
    """Return filename and storage path within the assets bucket."""
    parsed = urlparse(url)
    base = parsed.path.rsplit("/", 1)[-1] if parsed.path else ""
    name, ext = os.path.splitext(base)
    if not ext:
        ext = ".png"
    filename = f"{prediction_id}_{index}{ext}"

    segments: List[str] = ["all"]
    if folder_path:
        segments.extend(part for part in folder_path.split("/") if part)
    else:
        segments.append("replicate")
    segments.extend([prediction_id, filename])
    pseudo_path = "/".join(segments)

    return {"filename": filename, "path": pseudo_path}


async def _store_assets_for_prediction(
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
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:  # pragma: no cover
            metadata = {}
    folder_id = metadata.get("resolved_folder_id") or metadata.get("folder_id")
    folder_path = metadata.get("folder_path")
    source_task_id = metadata.get("task_id") or job.get("task_id")

    if folder_id and not folder_path:
        folder_info = _fetch_folder_info(supabase, folder_id, user_id)
        folder_path = _ltree_to_path(folder_info.get("path") if folder_info else None)  # type: ignore[union-attr]

    if not folder_id and folder_path:
        folder_id = _resolve_folder_id(
            supabase, user_id, None, _normalize_folder_path(folder_path)
        )
    if folder_id:
        folder_id = str(folder_id)

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
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        for index, url in enumerate(urls):
            cleaned_url = url.strip()
            if not cleaned_url or cleaned_url in existing_urls:
                continue

            try:
                response = await client.get(cleaned_url)
                response.raise_for_status()
            except Exception as exc:
                print(
                    f"[replicate_webhook] Failed to download asset {cleaned_url}: {exc}"
                )
                continue

            content_type = response.headers.get("content-type", "image/png")
            content_bytes = response.content
            fileinfo = _build_asset_fileinfo(
                prediction_id,
                index,
                cleaned_url,
                folder_path=folder_path,
            )
            storage_path = fileinfo["path"]

            try:
                upload_options = {
                    "content-type": content_type or "image/png",
                    "upsert": "true",
                }
                supabase.storage.from_("assets").upload(
                    storage_path,
                    content_bytes,
                    upload_options,
                )
            except Exception as exc:
                print(
                    f"[replicate_webhook] Failed to upload asset {storage_path} to bucket: {exc}"
                )
                continue

            asset_metadata = {
                "source": "replicate",
                "prediction_id": prediction_id,
                "external_url": cleaned_url,
                "folder_path": folder_path,
            }
            record: Dict[str, Any] = {
                "user_id": user_id,
                "bucket": "assets",
                "type": "image",
                "path": storage_path,
                "filename": fileinfo["filename"],
                "status": "ready",
                "mime_type": content_type,
                "size_bytes": len(content_bytes),
                "metadata": asset_metadata,
            }
            if folder_id:
                record["folder_id"] = folder_id
            if source_task_id:
                record["source_task_id"] = source_task_id
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

    supabase = get_supabase_client()
    normalized_folder_path = _normalize_folder_path(payload.folder_path)
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

    resolved_folder_id: Optional[str] = None
    resolved_folder_path: Optional[str] = normalized_folder_path
    if user_id:
        resolved_folder_id = _resolve_folder_id(
            supabase,
            user_id,
            payload.folder_id,
            normalized_folder_path,
        )
        if resolved_folder_id and not resolved_folder_path:
            folder_info = _fetch_folder_info(supabase, resolved_folder_id, user_id)
            resolved_folder_path = _ltree_to_path(
                folder_info.get("path") if folder_info else None  # type: ignore[union-attr]
            )

    job_record: Dict[str, Any] = {
        "prediction_id": prediction.id,
        "model": MODEL_ID,
        "prompt": payload.prompt,
        "status": prediction.status,
        "metadata": {
            **payload.model_dump(exclude={"prompt"}, exclude_none=True),
            "folder_path": resolved_folder_path,
            **({"resolved_folder_id": resolved_folder_id} if resolved_folder_id else {}),
        },
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

    data = _response_data(response)
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

    normalized_status_raw = status or "unknown"
    normalized_status = normalized_status_raw.lower()
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

    data = _response_data(response)

    if not data:
        print(
            f"[replicate_webhook] Prediction {prediction_id} not found when updating; "
            "attempting to insert fallback record."
        )
        try:
            insert_payload = {"prediction_id": prediction_id, **update_payload}
            response = supabase.table("replicate_jobs").insert(insert_payload).execute()
            data = _response_data(response)
        except Exception as exc:
            print(
                f"[replicate_webhook] Fallback insert failed for prediction {prediction_id}: {exc}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to persist replicate job: {exc}",
            ) from exc

    job_response = (
        supabase.table("replicate_jobs")
        .select("id, user_id, prompt, metadata")
        .eq("prediction_id", prediction_id)
        .limit(1)
        .execute()
    )
    job_data = _response_data(job_response)
    job_record = job_data[0] if job_data else None

    success_statuses = {"succeeded", "completed", "success"}
    urls = _extract_output_urls(payload.get("output"))
    if not urls and payload.get("urls"):
        urls = _extract_output_urls(payload.get("urls"))

    if job_record and urls and normalized_status in success_statuses:
        await _store_assets_for_prediction(supabase, job_record, prediction_id, urls)
    elif not job_record:
        print(
            f"[replicate_webhook] Unable to load job record for prediction {prediction_id}; "
            "skipping asset persistence."
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
