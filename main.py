from fastapi import FastAPI
from conexion import supabase

app = FastAPI(
    title="ContaPro Colombia",
    description="Sistema de gestión contable para negocios colombianos",
    version="1.0.0"
)


@app.get("/")
def inicio():
    return {
        "mensaje": "Bienvenido a ContaPro Colombia",
        "estado": "Servidor funcionando"
    }


@app.get("/empresas")
def listar_empresas():
    resultado = (
        supabase.table("empresas")
        .select("*")
        .execute()
    )

    return resultado.data
