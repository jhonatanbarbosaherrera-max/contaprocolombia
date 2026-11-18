"""Compatibilidad para módulos antiguos de ContaPro.

Usa la misma configuración central y nunca incorpora claves secretas.
Para consultar tablas protegidas, pasa el JWT del usuario a crear_cliente().
"""

from backend.app.database.supabase_client import crear_cliente

supabase = crear_cliente()
