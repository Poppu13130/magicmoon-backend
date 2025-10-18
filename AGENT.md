# AGENT NOTES

## Contexte général

- Service FastAPI déployé sur Cloud Run (`main.py`, router `routers/replicate_ai.py` pour la partie IA).
- Config via `.env` (Supabase, Replicate, etc.) chargée dans `core/config.py`.
- Auth côté API protégée par `verify_supabase_jwt`.
- Supabase client : `core/supabase_client.get_supabase_client()`.

## Workflow `routers/replicate_ai.py`

### Création de prédiction (`POST /ai/ideogram/predictions`)

- Requiert un JWT Supabase valide.
- Corps (`PredictionCreateIn`) :
  - champs ideogram (`prompt`, `resolution`, `style_type`, …)
  - `folder_id` *ou* `folder_path` (optionnels mais exclusifs) pour définir la destination.
- `folder_path` est normalisé (`a/b/c`). Si fourni et n’existe pas, l’API crée les entrées nécessaires dans la table `folders` (champ `path` ltree) pour l’utilisateur (et met `resolved_folder_id`).
- Enregistre le job dans `replicate_jobs` (avec métadonnées : folder_id/path résolus, prompts…).  
- `WEBHOOK_BASE_URL` doit pointer vers l’URL publique Cloud Run.

### Webhook Replicate (`POST /ai/webhooks/replicate`)

- Reçoit l’événement, met à jour `replicate_jobs` (status, output, erreurs, timestamps).
- Récupère les URLs d’output, télécharge chaque image (`httpx.AsyncClient`).
- Upload vers Supabase Storage bucket `assets` :
  - chemin : `assets/<USER_ID>/<folder_path?>/<prediction_id>/<filename>.png`
    - si pas de dossier : `assets/<USER_ID>/<prediction_id>/<filename>.png`
    - sinon, `folder_path` est inséré entre l’`user_id` et `prediction_id`.
  - Upload en `upsert` (`storage.from_("assets").upload(path, bytes, {"content-type": "...", "upsert": "true"})`).
- Insère/complète la ligne dans la table `assets` :
  - `user_id`, `bucket="assets"`, `path`, `filename`, `mime_type`, `size_bytes`.
  - `folder_id` si disponible (créé/résolu précédemment).
  - `metadata` contient `source="replicate"`, `prediction_id`, `external_url`, `folder_path`.

### Résolution des dossiers

- `_resolve_folder_id` accepte:
  - `folder_id`: validation qu’il appartient à l’utilisateur.
  - `folder_path`: création automatique via `_ensure_folder_path` si absent (utilise Supabase `folders`).
- `_fetch_folder_info` lit `folders.id / path` pour convertir en chemin slash (`_ltree_to_path`).

### Polling (`GET /ai/predictions/{id}`)

- Renvoie la ligne `replicate_jobs`.
- Vérifie que le `user_id` correspond à celui du token.

## Bonnes pratiques / conventions

- Toujours rappeler que `folder_id` **et** `folder_path` ne peuvent pas être envoyés simultanément (400 sinon).
- Upload Storage doit passer `content-type` (fallback `image/png`) et `upsert`.
- Les métadonnées dans Supabase peuvent revenir sous forme `str`; parser en JSON si besoin.
- Les logs `[replicate_webhook] ...` facilitent le debug Cloud Run (notamment upload / insert).

## Étapes futures possibles

- Ajouter/ou vérifier la création d’une entrée correspondante dans `folder_tree` si nécessaire (non fait actuellement).
- Gérer d’autres providers (ex. `ideogram`), en dupliquant la structure et en adaptant `MODEL_ID`.
- Ajouter signature webhook Replicate (`REPLICATE_WEBHOOK_SECRET`) si activée.

## Route `enhancor-crisp`

- Fichier : `routers/enhancor_crisp.py`.
- Endpoint : `POST /ai/enhancor-crisp`
  - Requiert JWT Supabase (`verify_supabase_jwt`).
  - Corps : `{ image_url: HttpUrl, folder_id?: str, folder_path?: str }` (`folder_id` XOR `folder_path`).
- Fonctionnement :
  - Résout/crée la hiérarchie dossier exactement comme `replicate_ai` (utilise `_normalize_folder_path`, `_resolve_folder_id`, etc.).
  - Exécute le modèle `recraft-ai/recraft-crisp-upscale` de manière synchrone (`replicate.run`).
  - Télécharge l’image générée, l’upload dans Supabase Storage `assets/<USER_ID>/<folder_path?>/<prediction_id>/<filename>`.
  - Insère la ressource dans la table `assets` (`metadata.source = "enhancor-crisp"`).
- Réponse : `status`, `file_url` (Replicate), `storage_path`, + info dossier.

## Déploiement

- `requirements.txt` doit contenir `httpx`, `fastapi`, `replicate`, `supabase`, etc.
- Après modifications, `pip install -r requirements.txt` puis `gcloud run deploy`.

Garder ce fichier à jour si l’on modifie la logique de stockage/dossiers ou si de nouvelles fonctionnalités impactent les conventions.
