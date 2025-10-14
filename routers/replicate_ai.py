from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import replicate
import os
from core.config import settings

# Configure le token pour le client Python
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
    webhook_events: list[str] = ["completed"]  # "start", "output", "logs", "completed"]

# ---------- 1) APPEL DIRECT (synchrone) ----------
@router.post("/ideogram/run-direct")
async def run_ideogram_direct(payload: IdeogramRunIn):
    """
    Lance le modèle et retourne directement l'URL du fichier résultat.
    Idéal pour tests/POC. En prod, préfère la version webhook.
    """
    try:
        output = replicate.run(
            "ideogram-ai/ideogram-character",
            input={
                "prompt": payload.prompt,
                "resolution": payload.resolution,
                "style_type": payload.style_type,
                "aspect_ratio": payload.aspect_ratio,
                "rendering_speed": payload.rendering_speed,
                "magic_prompt_option": payload.magic_prompt_option,
                "character_reference_image": payload.character_reference_image
            },
        )
        # La lib retourne un objet "file-like" moderne : .url() pour l’URL
        output_url = getattr(output, "url", None)
        if callable(output_url):
            output_url = output_url()
        elif output_url is None and isinstance(output, str):
            output_url = output
        return {"status": "succeeded", "output_url": output_url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------- 1b) Variante avec upload local ----------
@router.post("/ideogram/run-direct-upload")
async def run_ideogram_direct_upload(
    prompt: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Envoie un fichier local (UploadFile) comme character_reference_image.
    """
    try:
        # Pas besoin de sauvegarder sur disque : la lib accepte un file-like
        character_reference_image = file.file  # file-like object
        output = replicate.run(
            "ideogram-ai/ideogram-character",
            input={
                "prompt": prompt,
                "character_reference_image": character_reference_image
            },
        )
        output_url = getattr(output, "url", None)
        if callable(output_url):
            output_url = output_url()
        elif output_url is None and isinstance(output, str):
            output_url = output
        return {"status": "succeeded", "output_url": output_url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------- 2) CRÉATION DE PRÉDICTION + WEBHOOK ----------
@router.post("/ideogram/predictions")
async def create_prediction(payload: PredictionCreateIn):
    """
    Crée une prédiction Replicate et demande à Replicate d’appeler notre webhook.
    Retourne l'id de prédiction et status initial.
    """
    try:
        if not settings.WEBHOOK_BASE_URL:
            raise HTTPException(500, "WEBHOOK_BASE_URL non configuré")

        callback_url = f"{settings.WEBHOOK_BASE_URL}/ai/webhooks/replicate"
        prediction = replicate.predictions.create(
            model="ideogram-ai/ideogram-character",
            input={
                "prompt": payload.prompt,
                "resolution": payload.resolution,
                "style_type": payload.style_type,
                "aspect_ratio": payload.aspect_ratio,
                "rendering_speed": payload.rendering_speed,
                "magic_prompt_option": payload.magic_prompt_option,
                "character_reference_image": payload.character_reference_image,
            },
            webhook=callback_url,
            webhook_events_filter=payload.webhook_events,
        )
        # Tu peux persister prediction.id dans ta BDD ici (Supabase)
        # await save_prediction_in_db(prediction.id, status=prediction.status, ...)
        return {"prediction_id": prediction.id, "status": prediction.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------- 3) POLLING (récupérer l’état d’une prédiction) ----------
@router.get("/predictions/{prediction_id}")
async def get_prediction(prediction_id: str):
    try:
        p = replicate.predictions.get(prediction_id)
        # Si terminé, p.output peut contenir des fichiers (souvent liste)
        # NB: avec ce modèle .run retourne un handler .url(), ici via predictions, regarde p.output
        return {
            "id": p.id,
            "status": p.status,
            "output": p.output,  # parfois liste d'urls, ou objets fichiers
            "logs": p.logs,
            "error": p.error,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

# ---------- WEBHOOK RECEIVER ----------
@router.post("/webhooks/replicate")
async def replicate_webhook(request: Request):
    """
    Point d’entrée pour les webhooks Replicate.
    Événements possibles: start, output, logs, completed (selon webhook_events_filter).
    """
    # (Optionnel) Vérif signature si tu actives la signature côté Replicate:
    # doc: "Verifying webhooks" (mets le secret dans settings.REPLICATE_WEBHOOK_SECRET)
    # Exemple de squelette (dépend de la mécanique de Replicate, adapte si nécessaire) :
    # signature = request.headers.get("Replicate-Signature", "")
    # body = await request.body()
    # if not verify_signature(signature, body, settings.REPLICATE_WEBHOOK_SECRET):
    #     raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    # Exemple de forme attendue :
    # {
    #   "id": "z3wbih3bs64of...",
    #   "status": "completed",
    #   "output": [...],  # souvent des urls
    #   "logs": "...",
    #   ...
    # }

    prediction_id = payload.get("id")
    status = payload.get("status")
    output = payload.get("output")

    # ➜ Ici, en pratique, tu mets à jour ta BDD (Supabase) avec (status, output)
    # await update_prediction_in_db(prediction_id, status, output)

    # Tu peux déclencher un post-traitement (upload vers Supabase Storage, etc.)

    return JSONResponse({"ok": True, "prediction_id": prediction_id, "status": status})
