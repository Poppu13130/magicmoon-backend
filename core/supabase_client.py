from functools import lru_cache

from supabase import Client, create_client

from core.config import settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return a singleton Supabase client configured from settings."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
