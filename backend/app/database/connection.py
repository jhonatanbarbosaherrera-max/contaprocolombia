"""Utilidades de conexión para ContaPro Colombia.

Las consultas a tablas protegidas deben ejecutarse con el JWT del usuario
autenticado; no se debe consultar información empresarial sin sesión.
"""

from backend.app.database.supabase_client import crear_cliente


def comprobar_acceso_usuario(access_token):
    if not access_token:
        raise ValueError("Se requiere el token de un usuario autenticado.")

    cliente = crear_cliente(access_token)
    usuario = cliente.auth.get_user(access_token)
    return {
        "conectado": True,
        "usuario_id": usuario.user.id,
    }
