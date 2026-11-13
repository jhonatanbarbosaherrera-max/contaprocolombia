import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

supabase = create_client(url, key)

try:
    resultado = (
        supabase.table("empresas")
        .select("*")
        .limit(5)
        .execute()
    )

    print("CONEXION EXITOSA")
    print("Empresas encontradas:", len(resultado.data))

except Exception as error:
    print("ERROR DE CONEXION:")
    print(error)