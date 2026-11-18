import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")

if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
    raise RuntimeError(
        "Configura SUPABASE_URL y SUPABASE_PUBLISHABLE_KEY en el archivo .env."
    )


def crear_cliente(token=None):
    """Crea un cliente Supabase y, si existe, aplica el JWT del usuario."""
    cliente = create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)

    if token:
        cliente.postgrest.auth(token)

    return cliente


def renovar_sesion(refresh_token):
    """Renueva la sesión de Supabase usando la publishable key."""
    cliente = create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)
    resultado = cliente.auth.refresh_session(refresh_token)
    return resultado.session
