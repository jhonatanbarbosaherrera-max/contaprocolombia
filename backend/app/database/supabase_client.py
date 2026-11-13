
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


BASE_DIR = Path(__file__).resolve().parents[3]

load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "Faltan las variables de conexion de Supabase."
    )


def crear_cliente(token=None):
    cliente = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
    )

    if token:
        cliente.postgrest.auth(token)

    return cliente


def renovar_sesion(refresh_token):
    cliente = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
    )

    resultado = cliente.auth.refresh_session(
        refresh_token
    )

    return resultado.session
