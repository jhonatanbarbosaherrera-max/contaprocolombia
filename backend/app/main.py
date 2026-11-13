
import base64
import json
import time
from pathlib import Path
from datetime import date

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.database.supabase_client import (
    crear_cliente,
    renovar_sesion,
)

from backend.app.ventas import router as ventas_router


app = FastAPI(
    title="ContaPro Colombia",
    description="Sistema de gestion empresarial y contabilidad",
    version="1.0.0",
)

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR / "static"),
    name="static",
)

templates = Jinja2Templates(
    directory=str(FRONTEND_DIR / "templates")
)

# Rutas del nuevo modulo de ventas
app.include_router(ventas_router)


# =====================================================
# RENOVACION AUTOMATICA DE SESION
# =====================================================

def obtener_expiracion_token(token):
    partes = token.split(".")

    if len(partes) != 3:
        raise ValueError("El token no tiene un formato valido.")

    payload = partes[1]
    payload += "=" * (-len(payload) % 4)

    datos = json.loads(
        base64.urlsafe_b64decode(payload.encode("utf-8"))
    )

    return int(datos.get("exp", 0))


def configurar_cookie(respuesta, nombre, valor, max_age):
    respuesta.set_cookie(
        key=nombre,
        value=valor,
        max_age=max_age,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )


@app.middleware("http")
async def renovar_sesion_automatica(request: Request, call_next):
    rutas_publicas = (
        "/login",
        "/static",
        "/salud",
        "/favicon.ico",
    )

    ruta = request.url.path

    if any(
        ruta == publica or ruta.startswith(publica + "/")
        for publica in rutas_publicas
    ):
        return await call_next(request)

    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    sesion_renovada = None

    if access_token or refresh_token:
        necesita_renovar = False

        if not access_token:
            necesita_renovar = True
        else:
            try:
                expiracion = obtener_expiracion_token(
                    access_token
                )

                if expiracion <= int(time.time()) + 60:
                    necesita_renovar = True

            except Exception:
                necesita_renovar = True

        if necesita_renovar:
            if not refresh_token:
                respuesta = RedirectResponse(
                    "/login",
                    status_code=303,
                )

                respuesta.delete_cookie(
                    "access_token",
                    path="/",
                )
                respuesta.delete_cookie(
                    "refresh_token",
                    path="/",
                )

                return respuesta

            try:
                sesion_renovada = renovar_sesion(
                    refresh_token
                )

                if (
                    not sesion_renovada
                    or not sesion_renovada.access_token
                    or not sesion_renovada.refresh_token
                ):
                    raise ValueError(
                        "Supabase no devolvio una sesion renovada."
                    )

                cookies = dict(request.cookies)

                cookies["access_token"] = (
                    sesion_renovada.access_token
                )

                cookies["refresh_token"] = (
                    sesion_renovada.refresh_token
                )

                request._cookies = cookies

            except Exception as error:
                print(
                    "Error al renovar la sesion:",
                    repr(error),
                )

                respuesta = RedirectResponse(
                    "/login",
                    status_code=303,
                )

                respuesta.delete_cookie(
                    "access_token",
                    path="/",
                )
                respuesta.delete_cookie(
                    "refresh_token",
                    path="/",
                )

                return respuesta

    respuesta = await call_next(request)

    if sesion_renovada:
        duracion = int(
            getattr(sesion_renovada, "expires_in", 3600)
            or 3600
        )

        configurar_cookie(
            respuesta,
            "access_token",
            sesion_renovada.access_token,
            duracion,
        )

        configurar_cookie(
            respuesta,
            "refresh_token",
            sesion_renovada.refresh_token,
            60 * 60 * 24 * 30,
        )

    return respuesta


# =====================================================
# FUNCIONES GENERALES
# =====================================================

def buscar_empresa(token):
    cliente = crear_cliente(token)
    cliente.auth.get_user(token)

    resultado = (
        cliente.table("empresas")
        .select("id, nombre")
        .limit(1)
        .execute()
    )

    return resultado.data or []


def obtener_resumen(token, empresa_id):
    cliente = crear_cliente(token)

    ingresos = (
        cliente.table("ingresos")
        .select("valor")
        .eq("empresa_id", empresa_id)
        .execute()
    )

    gastos = (
        cliente.table("gastos")
        .select("valor")
        .eq("empresa_id", empresa_id)
        .execute()
    )

    productos = (
        cliente.table("productos")
        .select("id", count="exact")
        .eq("empresa_id", empresa_id)
        .execute()
    )

    total_ingresos = sum(
        float(fila["valor"] or 0)
        for fila in ingresos.data or []
    )

    total_gastos = sum(
        float(fila["valor"] or 0)
        for fila in gastos.data or []
    )

    ganancia = total_ingresos - total_gastos

    return {
        "ingresos": f"$ {total_ingresos:,.0f}".replace(",", "."),
        "gastos": f"$ {total_gastos:,.0f}".replace(",", "."),
        "ganancia": f"$ {ganancia:,.0f}".replace(",", "."),
        "productos": productos.count or 0,
    }


def obtener_clientes(token, empresa_id):
    cliente = crear_cliente(token)

    resultado = (
        cliente.table("clientes")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("created_at", desc=True)
        .execute()
    )

    return resultado.data or []


def obtener_proveedores(token, empresa_id):
    cliente = crear_cliente(token)

    resultado = (
        cliente.table("proveedores")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("created_at", desc=True)
        .execute()
    )

    return resultado.data or []


def obtener_cuentas_activas(token, empresa_id):
    cliente = crear_cliente(token)

    resultado = (
        cliente.table("cuentas_financieras")
        .select("id, nombre, tipo, entidad")
        .eq("empresa_id", empresa_id)
        .eq("activo", True)
        .order("created_at", desc=True)
        .execute()
    )

    return resultado.data or []


def validar_cuenta(token, empresa_id, cuenta_id):
    cliente = crear_cliente(token)

    resultado = (
        cliente.table("cuentas_financieras")
        .select("id, nombre")
        .eq("id", cuenta_id)
        .eq("empresa_id", empresa_id)
        .eq("activo", True)
        .execute()
    )

    if not resultado.data:
        raise ValueError(
            "La cuenta seleccionada no existe o está inactiva."
        )

    return resultado.data[0]


# =====================================================
# FUNCIONES DE COMPRAS
# =====================================================

def obtener_productos(token, empresa_id):
    cliente = crear_cliente(token)

    resultado = (
        cliente.table("productos")
        .select("id, nombre, codigo, precio_compra, stock")
        .eq("empresa_id", empresa_id)
        .order("nombre")
        .execute()
    )

    return resultado.data or []


def obtener_compras(token, empresa_id):
    cliente = crear_cliente(token)

    resultado = (
        cliente.table("compras")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("created_at", desc=True)
        .execute()
    )

    return resultado.data or []


def cargar_pagina_compras(request, token, empresa_id, error=None):
    proveedores = obtener_proveedores(token, empresa_id)
    productos = obtener_productos(token, empresa_id)
    compras = obtener_compras(token, empresa_id)

    return templates.TemplateResponse(
        request=request,
        name="compras.html",
        context={
            "proveedores": proveedores,
            "productos": productos,
            "compras": compras,
            "error": error,
        },
    )


# =====================================================
# INICIO Y PANEL PRINCIPAL
# =====================================================

@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        empresa = empresas[0]
        resumen = obtener_resumen(token, empresa["id"])

        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "empresa": empresa["nombre"],
                "resumen": resumen,
            },
        )

    except Exception as error:
        print("Error al cargar el panel:", repr(error))

        return HTMLResponse(
            "<h2>Error al cargar ContaPro</h2>"
            "<p>Revisa la terminal para conocer el problema.</p>"
            "<a href='/'>Volver a intentar</a>",
            status_code=500,
        )


# =====================================================
# INICIO DE SESION
# =====================================================

@app.get("/login", response_class=HTMLResponse)
def mostrar_login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None},
    )


@app.post("/login")
def iniciar_sesion(
    email: str = Form(...),
    password: str = Form(...),
):
    try:
        cliente = crear_cliente()

        resultado = cliente.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })

        sesion = resultado.session

        respuesta = RedirectResponse(
            "/",
            status_code=303,
        )

        duracion = int(
            getattr(sesion, "expires_in", 3600) or 3600
        )

        configurar_cookie(
            respuesta,
            "access_token",
            sesion.access_token,
            duracion,
        )

        configurar_cookie(
            respuesta,
            "refresh_token",
            sesion.refresh_token,
            60 * 60 * 24 * 30,
        )

        return respuesta

    except Exception as error:
        print("Error al iniciar sesion:", repr(error))

        return HTMLResponse(
            "<h2>No se pudo iniciar sesion</h2>"
            "<a href='/login'>Volver</a>",
            status_code=401,
        )


@app.get("/logout")
def cerrar_sesion():
    respuesta = RedirectResponse(
        "/login",
        status_code=303,
    )

    respuesta.delete_cookie(
        "access_token",
        path="/",
    )

    respuesta.delete_cookie(
        "refresh_token",
        path="/",
    )

    return respuesta


# =====================================================
# EMPRESA
# =====================================================

@app.get("/empresa", response_class=HTMLResponse)
def mostrar_empresa(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        if buscar_empresa(token):
            return RedirectResponse("/", status_code=303)

        return templates.TemplateResponse(
            request=request,
            name="empresa.html",
            context={"error": None},
        )

    except Exception as error:
        print("Error al consultar empresa:", repr(error))
        return RedirectResponse("/login", status_code=303)


@app.post("/empresa", response_class=HTMLResponse)
def registrar_empresa(
    request: Request,
    nombre: str = Form(...),
    nit: str = Form(...),
    telefono: str = Form(...),
    correo: str = Form(...),
    direccion: str = Form(...),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        cliente = crear_cliente(token)
        cliente.auth.get_user(token)

        empresas = (
            cliente.table("empresas")
            .select("id")
            .limit(1)
            .execute()
        )

        if empresas.data:
            return RedirectResponse("/", status_code=303)

        cliente.table("empresas").insert({
            "nombre": nombre,
            "nit": nit,
            "telefono": telefono,
            "correo": correo,
            "direccion": direccion,
        }).execute()

        return RedirectResponse("/", status_code=303)

    except Exception as error:
        print("Error al guardar empresa:", repr(error))

        return templates.TemplateResponse(
            request=request,
            name="empresa.html",
            context={
                "error": (
                    "No se pudo guardar la empresa. "
                    "Verifica los datos y vuelve a intentarlo."
                )
            },
            status_code=400,
        )


# =====================================================
# GASTOS
# =====================================================

@app.get("/gastos", response_class=HTMLResponse)
def mostrar_gastos(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cuentas = obtener_cuentas_activas(
            token,
            empresas[0]["id"],
        )

        return templates.TemplateResponse(
            request=request,
            name="gastos.html",
            context={
                "error": None,
                "cuentas": cuentas,
            },
        )

    except Exception as error:
        print("Error al cargar gastos:", repr(error))

        return HTMLResponse(
            "<h2>Error al cargar gastos</h2>"
            "<a href='/'>Volver al panel</a>",
            status_code=400,
        )


@app.post("/gastos", response_class=HTMLResponse)
def registrar_gasto(
    request: Request,
    descripcion: str = Form(...),
    valor: float = Form(...),
    fecha: str = Form(...),
    metodo_pago: str = Form(...),
    cuenta_id: str = Form(...),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    empresas = []

    try:
        if not descripcion.strip():
            raise ValueError("La descripción es obligatoria.")

        if valor <= 0:
            raise ValueError("El valor debe ser mayor que cero.")

        if not fecha.strip():
            raise ValueError("Selecciona la fecha del gasto.")

        if not metodo_pago.strip():
            raise ValueError("Selecciona el método de pago.")

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        empresa_id = empresas[0]["id"]

        validar_cuenta(token, empresa_id, cuenta_id)

        cliente = crear_cliente(token)

        cliente.table("gastos").insert({
            "empresa_id": empresa_id,
            "cuenta_id": cuenta_id,
            "descripcion": descripcion.strip(),
            "valor": valor,
            "fecha": fecha,
            "metodo_pago": metodo_pago,
        }).execute()

        return RedirectResponse("/gastos", status_code=303)

    except Exception as error:
        print("Error al registrar gasto:", repr(error))

        cuentas = []

        try:
            if empresas:
                cuentas = obtener_cuentas_activas(
                    token,
                    empresas[0]["id"],
                )
        except Exception as error_cuentas:
            print("Error al cargar cuentas:", repr(error_cuentas))

        return templates.TemplateResponse(
            request=request,
            name="gastos.html",
            context={
                "error": (
                    "No se pudo registrar el gasto. "
                    "Verifica los datos y la cuenta seleccionada."
                ),
                "cuentas": cuentas,
            },
            status_code=400,
        )


# =====================================================
# INVENTARIO
# =====================================================

@app.get("/inventario", response_class=HTMLResponse)
def mostrar_inventario(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        resultado = (
            cliente.table("productos")
            .select("*")
            .eq("empresa_id", empresas[0]["id"])
            .order("created_at", desc=True)
            .execute()
        )

        return templates.TemplateResponse(
            request=request,
            name="inventario.html",
            context={
                "error": None,
                "productos": resultado.data or [],
            },
        )

    except Exception as error:
        print("Error al consultar inventario:", repr(error))

        return templates.TemplateResponse(
            request=request,
            name="inventario.html",
            context={
                "error": "No se pudieron consultar los productos.",
                "productos": [],
            },
            status_code=400,
        )


@app.post("/inventario", response_class=HTMLResponse)
def registrar_producto(
    request: Request,
    nombre: str = Form(...),
    codigo: str = Form(""),
    descripcion: str = Form(""),
    precio_compra: float = Form(...),
    precio_venta: float = Form(...),
    stock: int = Form(...),
    stock_minimo: int = Form(...),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio.")

        if (
            precio_compra < 0
            or precio_venta < 0
            or stock < 0
            or stock_minimo < 0
        ):
            raise ValueError("Los valores no pueden ser negativos.")

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        cliente.table("productos").insert({
            "empresa_id": empresas[0]["id"],
            "nombre": nombre.strip(),
            "codigo": codigo.strip() or None,
            "descripcion": descripcion.strip() or None,
            "precio_compra": precio_compra,
            "precio_venta": precio_venta,
            "stock": stock,
            "stock_minimo": stock_minimo,
            "activo": True,
        }).execute()

        return RedirectResponse("/inventario", status_code=303)

    except Exception as error:
        print("Error al registrar producto:", repr(error))

        return templates.TemplateResponse(
            request=request,
            name="inventario.html",
            context={
                "error": (
                    "No se pudo registrar el producto. "
                    "Verifica los datos e intentalo nuevamente."
                ),
                "productos": [],
            },
            status_code=400,
        )


@app.post("/inventario/editar/{producto_id}")
def editar_producto(
    request: Request,
    producto_id: str,
    nombre: str = Form(...),
    codigo: str = Form(""),
    descripcion: str = Form(""),
    precio_compra: float = Form(...),
    precio_venta: float = Form(...),
    stock: int = Form(...),
    stock_minimo: int = Form(...),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio.")

        if (
            precio_compra < 0
            or precio_venta < 0
            or stock < 0
            or stock_minimo < 0
        ):
            raise ValueError("Los valores no pueden ser negativos.")

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        cliente.table("productos").update({
            "nombre": nombre.strip(),
            "codigo": codigo.strip() or None,
            "descripcion": descripcion.strip() or None,
            "precio_compra": precio_compra,
            "precio_venta": precio_venta,
            "stock": stock,
            "stock_minimo": stock_minimo,
        }).eq(
            "id", producto_id
        ).eq(
            "empresa_id", empresas[0]["id"]
        ).execute()

        return RedirectResponse("/inventario", status_code=303)

    except Exception as error:
        print("Error al editar producto:", repr(error))
        return RedirectResponse("/inventario", status_code=303)


@app.post("/inventario/eliminar/{producto_id}")
def eliminar_producto(
    request: Request,
    producto_id: str,
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        cliente.table("productos").delete().eq(
            "id", producto_id
        ).eq(
            "empresa_id", empresas[0]["id"]
        ).execute()

        return RedirectResponse("/inventario", status_code=303)

    except Exception as error:
        print("Error al eliminar producto:", repr(error))
        return RedirectResponse("/inventario", status_code=303)


# =====================================================
# CLIENTES
# =====================================================

@app.get("/clientes", response_class=HTMLResponse)
def mostrar_clientes(request: Request, buscar: str = ""):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        clientes = obtener_clientes(token, empresas[0]["id"])
        termino = buscar.strip().casefold()

        if termino:
            clientes = [
                cliente for cliente in clientes
                if termino in str(cliente.get("nombre") or "").casefold()
                or termino in str(cliente.get("documento") or "").casefold()
                or termino in str(cliente.get("telefono") or "").casefold()
                or termino in str(cliente.get("correo") or "").casefold()
            ]

        return templates.TemplateResponse(
            request=request,
            name="clientes.html",
            context={
                "clientes": clientes,
                "error": None,
                "buscar": buscar,
            },
        )

    except Exception as error:
        print("Error al consultar clientes:", repr(error))

        return HTMLResponse(
            "<h2>Error al consultar clientes</h2>"
            "<p>Revisa la terminal para conocer el problema.</p>"
            "<a href='/'>Volver</a>",
            status_code=400,
        )


@app.post("/clientes")
def registrar_cliente(
    request: Request,
    nombre: str = Form(...),
    documento: str = Form(""),
    telefono: str = Form(""),
    correo: str = Form(""),
    direccion: str = Form(""),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio.")

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        cliente.table("clientes").insert({
            "empresa_id": empresas[0]["id"],
            "nombre": nombre.strip(),
            "documento": documento.strip() or None,
            "telefono": telefono.strip() or None,
            "correo": correo.strip() or None,
            "direccion": direccion.strip() or None,
        }).execute()

        return RedirectResponse("/clientes", status_code=303)

    except Exception as error:
        print("Error al registrar cliente:", repr(error))
        return RedirectResponse("/clientes", status_code=303)


@app.post("/clientes/editar/{cliente_id}")
def editar_cliente(
    request: Request,
    cliente_id: str,
    nombre: str = Form(...),
    documento: str = Form(""),
    telefono: str = Form(""),
    correo: str = Form(""),
    direccion: str = Form(""),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio.")

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        cliente.table("clientes").update({
            "nombre": nombre.strip(),
            "documento": documento.strip() or None,
            "telefono": telefono.strip() or None,
            "correo": correo.strip() or None,
            "direccion": direccion.strip() or None,
        }).eq(
            "id", cliente_id
        ).eq(
            "empresa_id", empresas[0]["id"]
        ).execute()

        return RedirectResponse("/clientes", status_code=303)

    except Exception as error:
        print("Error al editar cliente:", repr(error))
        return RedirectResponse("/clientes", status_code=303)


@app.post("/clientes/eliminar/{cliente_id}")
def eliminar_cliente(
    request: Request,
    cliente_id: str,
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        cliente.table("clientes").delete().eq(
            "id", cliente_id
        ).eq(
            "empresa_id", empresas[0]["id"]
        ).execute()

        return RedirectResponse("/clientes", status_code=303)

    except Exception as error:
        print("Error al eliminar cliente:", repr(error))
        return RedirectResponse("/clientes", status_code=303)


# =====================================================
# PROVEEDORES
# =====================================================

@app.get("/proveedores", response_class=HTMLResponse)
def mostrar_proveedores(request: Request, buscar: str = ""):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        proveedores = obtener_proveedores(
            token,
            empresas[0]["id"],
        )

        termino = buscar.strip().casefold()

        if termino:
            proveedores = [
                proveedor for proveedor in proveedores
                if termino in str(proveedor.get("nombre") or "").casefold()
                or termino in str(proveedor.get("documento") or "").casefold()
                or termino in str(proveedor.get("telefono") or "").casefold()
                or termino in str(proveedor.get("correo") or "").casefold()
            ]

        return templates.TemplateResponse(
            request=request,
            name="proveedores.html",
            context={
                "proveedores": proveedores,
                "error": None,
                "buscar": buscar,
            },
        )

    except Exception as error:
        print("Error al consultar proveedores:", repr(error))

        return HTMLResponse(
            "<h2>Error al consultar proveedores</h2>"
            "<p>Revisa la terminal para conocer el problema.</p>"
            "<a href='/'>Volver</a>",
            status_code=400,
        )


@app.post("/proveedores")
def registrar_proveedor(
    request: Request,
    nombre: str = Form(...),
    documento: str = Form(""),
    telefono: str = Form(""),
    correo: str = Form(""),
    direccion: str = Form(""),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio.")

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        cliente.table("proveedores").insert({
            "empresa_id": empresas[0]["id"],
            "nombre": nombre.strip(),
            "documento": documento.strip() or None,
            "telefono": telefono.strip() or None,
            "correo": correo.strip() or None,
            "direccion": direccion.strip() or None,
        }).execute()

        return RedirectResponse("/proveedores", status_code=303)

    except Exception as error:
        print("Error al registrar proveedor:", repr(error))
        return RedirectResponse("/proveedores", status_code=303)


@app.post("/proveedores/editar/{proveedor_id}")
def editar_proveedor(
    request: Request,
    proveedor_id: str,
    nombre: str = Form(...),
    documento: str = Form(""),
    telefono: str = Form(""),
    correo: str = Form(""),
    direccion: str = Form(""),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio.")

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        cliente.table("proveedores").update({
            "nombre": nombre.strip(),
            "documento": documento.strip() or None,
            "telefono": telefono.strip() or None,
            "correo": correo.strip() or None,
            "direccion": direccion.strip() or None,
        }).eq(
            "id", proveedor_id
        ).eq(
            "empresa_id", empresas[0]["id"]
        ).execute()

        return RedirectResponse("/proveedores", status_code=303)

    except Exception as error:
        print("Error al editar proveedor:", repr(error))
        return RedirectResponse("/proveedores", status_code=303)


@app.post("/proveedores/eliminar/{proveedor_id}")
def eliminar_proveedor(
    request: Request,
    proveedor_id: str,
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        cliente = crear_cliente(token)

        cliente.table("proveedores").delete().eq(
            "id", proveedor_id
        ).eq(
            "empresa_id", empresas[0]["id"]
        ).execute()

        return RedirectResponse("/proveedores", status_code=303)

    except Exception as error:
        print("Error al eliminar proveedor:", repr(error))
        return RedirectResponse("/proveedores", status_code=303)


# =====================================================
# COMPRAS
# =====================================================

@app.get("/compras", response_class=HTMLResponse)
def mostrar_compras(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        return cargar_pagina_compras(
            request,
            token,
            empresas[0]["id"],
        )

    except Exception as error:
        print("Error al consultar compras:", repr(error))

        return HTMLResponse(
            "<h2>Error al consultar compras</h2>"
            "<p>Revisa la terminal para conocer el problema.</p>"
            "<a href='/'>Volver</a>",
            status_code=400,
        )


@app.post("/compras")
def registrar_compra(
    request: Request,
    proveedor_id: str = Form(...),
    producto_id: list[str] = Form(...),
    cantidad: list[float] = Form(...),
    precio_unitario: list[float] = Form(...),
    fecha: str = Form(...),
    metodo_pago: str = Form(...),
    descripcion: str = Form(""),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        cliente = crear_cliente(token)
        usuario = cliente.auth.get_user(token)
        usuario_id = usuario.user.id

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        empresa_id = empresas[0]["id"]

        if not (
            len(producto_id)
            == len(cantidad)
            == len(precio_unitario)
        ):
            raise ValueError(
                "Los productos tienen datos incompletos."
            )

        if not producto_id:
            raise ValueError(
                "Debes agregar al menos un producto."
            )

        if not fecha.strip():
            raise ValueError("Selecciona la fecha de compra.")

        if not metodo_pago.strip():
            raise ValueError("Selecciona el método de pago.")

        proveedor = (
            cliente.table("proveedores")
            .select("id")
            .eq("id", proveedor_id)
            .eq("empresa_id", empresa_id)
            .execute()
        )

        if not proveedor.data:
            raise ValueError(
                "El proveedor seleccionado no existe."
            )

        detalles_por_producto = {}

        for i in range(len(producto_id)):
            id_producto = producto_id[i]
            cantidad_producto = float(cantidad[i])
            precio = float(precio_unitario[i])

            if cantidad_producto <= 0:
                raise ValueError(
                    "La cantidad debe ser mayor que cero."
                )

            if not cantidad_producto.is_integer():
                raise ValueError(
                    "La cantidad debe ser un número entero."
                )

            if precio <= 0:
                raise ValueError(
                    "El precio debe ser mayor que cero."
                )

            producto = (
                cliente.table("productos")
                .select("id, nombre, stock")
                .eq("id", id_producto)
                .eq("empresa_id", empresa_id)
                .execute()
            )

            if not producto.data:
                raise ValueError(
                    "Uno de los productos seleccionados no existe."
                )

            if id_producto not in detalles_por_producto:
                detalles_por_producto[id_producto] = {
                    "producto_id": id_producto,
                    "nombre": producto.data[0]["nombre"],
                    "cantidad": 0,
                    "precio_unitario": precio,
                    "stock_anterior": float(
                        producto.data[0]["stock"] or 0
                    ),
                }

            detalles_por_producto[id_producto]["cantidad"] += (
                cantidad_producto
            )

            detalles_por_producto[id_producto][
                "precio_unitario"
            ] = precio

        detalles = []
        total = 0

        for detalle in detalles_por_producto.values():
            subtotal = (
                detalle["cantidad"]
                * detalle["precio_unitario"]
            )

            detalle["subtotal"] = subtotal
            total += subtotal
            detalles.append(detalle)

        if total <= 0:
            raise ValueError(
                "El total de la compra debe ser mayor que cero."
            )

        descripcion_final = (
            descripcion.strip() or "Compra de productos"
        )

        resultado_compra = (
            cliente.table("compras")
            .insert({
                "usuario_id": usuario_id,
                "empresa_id": empresa_id,
                "proveedor_id": proveedor_id,
                "fecha": fecha,
                "descripcion": descripcion_final,
                "total": total,
            })
            .execute()
        )

        if not resultado_compra.data:
            raise ValueError(
                "Supabase no devolvió el registro de la compra."
            )

        compra_id = resultado_compra.data[0]["id"]

        registros_detalle = []

        for detalle in detalles:
            registros_detalle.append({
                "compra_id": compra_id,
                "usuario_id": usuario_id,
                "empresa_id": empresa_id,
                "producto_id": detalle["producto_id"],
                "cantidad": detalle["cantidad"],
                "precio_unitario": detalle["precio_unitario"],
                "subtotal": detalle["subtotal"],
            })

        cliente.table("detalle_compras").insert(
            registros_detalle
        ).execute()

        for detalle in detalles:
            nuevo_stock = (
                detalle["stock_anterior"]
                + detalle["cantidad"]
            )

            cliente.table("productos").update({
                "stock": nuevo_stock,
                "precio_compra": detalle["precio_unitario"],
            }).eq(
                "id", detalle["producto_id"]
            ).eq(
                "empresa_id", empresa_id
            ).execute()

        # La compra se registra como gasto una sola vez.
        cliente.table("gastos").insert({
            "empresa_id": empresa_id,
            "descripcion": (
                "Compra a proveedor: " + descripcion_final
            ),
            "valor": total,
            "fecha": fecha,
            "metodo_pago": metodo_pago,
        }).execute()

        return RedirectResponse("/compras", status_code=303)

    except Exception as error:
        print("ERROR AL REGISTRAR COMPRA:", repr(error))

        mensaje = str(error)

        try:
            empresas = buscar_empresa(token)

            if empresas:
                return cargar_pagina_compras(
                    request,
                    token,
                    empresas[0]["id"],
                    error=(
                        "No se pudo completar la compra: "
                        + mensaje
                    ),
                )

        except Exception as error_pagina:
            print(
                "Error al volver a cargar compras:",
                repr(error_pagina),
            )

        return HTMLResponse(
            "<h2>No se pudo registrar la compra</h2>"
            "<p>Revisa la terminal de Python para conocer el error.</p>"
            "<a href='/compras'>Volver a compras</a>",
            status_code=400,
        )


# =====================================================
# COMPROBACION DEL SERVIDOR
# =====================================================

@app.get("/salud")
def salud():
    return {"estado": "correcto"}


# =====================================================
# CAJA Y BANCOS
# =====================================================

def cargar_datos_caja(token, empresa_id):
    cliente = crear_cliente(token)

    resultado_cuentas = (
        cliente.table("cuentas_financieras")
        .select("*")
        .eq("empresa_id", empresa_id)
        .eq("activo", True)
        .order("created_at", desc=True)
        .execute()
    )

    resultado_movimientos = (
        cliente.table("movimientos_financieros")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("fecha", desc=True)
        .order("created_at", desc=True)
        .execute()
    )

    resultado_ingresos = (
        cliente.table("ingresos")
        .select(
            "id, cuenta_id, descripcion, valor, fecha, "
            "referencia, created_at"
        )
        .eq("empresa_id", empresa_id)
        .not_.is_("cuenta_id", "null")
        .execute()
    )

    resultado_gastos = (
        cliente.table("gastos")
        .select(
            "id, cuenta_id, descripcion, valor, fecha, "
            "referencia, created_at"
        )
        .eq("empresa_id", empresa_id)
        .not_.is_("cuenta_id", "null")
        .execute()
    )

    cuentas = resultado_cuentas.data or []
    movimientos_manuales = resultado_movimientos.data or []
    ingresos = resultado_ingresos.data or []
    gastos = resultado_gastos.data or []

    saldos = {}

    for cuenta in cuentas:
        saldos[cuenta["id"]] = float(
            cuenta.get("saldo_inicial") or 0
        )

    movimientos_historial = []

    for ingreso in ingresos:
        cuenta_id = ingreso.get("cuenta_id")
        valor = float(ingreso.get("valor") or 0)

        if cuenta_id in saldos:
            saldos[cuenta_id] += valor

        movimientos_historial.append({
            "fecha": ingreso.get("fecha"),
            "descripcion": ingreso.get("descripcion") or "Venta",
            "tipo": "ingreso",
            "valor": valor,
            "referencia": ingreso.get("referencia"),
            "origen": "Venta",
            "created_at": ingreso.get("created_at"),
        })

    for gasto in gastos:
        cuenta_id = gasto.get("cuenta_id")
        valor = float(gasto.get("valor") or 0)

        if cuenta_id in saldos:
            saldos[cuenta_id] -= valor

        movimientos_historial.append({
            "fecha": gasto.get("fecha"),
            "descripcion": gasto.get("descripcion") or "Gasto",
            "tipo": "egreso",
            "valor": valor,
            "referencia": gasto.get("referencia"),
            "origen": "Gasto",
            "created_at": gasto.get("created_at"),
        })

    for movimiento in movimientos_manuales:
        cuenta_id = movimiento.get("cuenta_id")
        valor = float(movimiento.get("valor") or 0)

        if cuenta_id in saldos:
            if movimiento.get("tipo") == "ingreso":
                saldos[cuenta_id] += valor
            elif movimiento.get("tipo") == "egreso":
                saldos[cuenta_id] -= valor

        movimientos_historial.append({
            "fecha": movimiento.get("fecha"),
            "descripcion": (
                movimiento.get("descripcion")
                or "Movimiento manual"
            ),
            "tipo": movimiento.get("tipo"),
            "valor": valor,
            "referencia": movimiento.get("referencia"),
            "observaciones": movimiento.get("observaciones"),
            "origen": "Movimiento manual",
            "created_at": movimiento.get("created_at"),
        })

    for cuenta in cuentas:
        saldo = saldos.get(cuenta["id"], 0)

        cuenta["saldo_actual"] = saldo
        cuenta["saldo_formateado"] = (
            "$ " + f"{saldo:,.0f}".replace(",", ".")
        )

    movimientos_historial.sort(
        key=lambda movimiento: (
            str(movimiento.get("fecha") or ""),
            str(movimiento.get("created_at") or ""),
        ),
        reverse=True,
    )

    total_saldos = sum(saldos.values())

    return {
        "cuentas": cuentas,
        "movimientos": movimientos_historial,
        "total_saldos": total_saldos,
        "total_formateado": (
            "$ " + f"{total_saldos:,.0f}".replace(",", ".")
        ),
    }


def cargar_pagina_caja(request, token, empresa_id, error=None):
    datos = cargar_datos_caja(token, empresa_id)

    return templates.TemplateResponse(
        request=request,
        name="caja_bancos.html",
        context={
            "cuentas": datos["cuentas"],
            "movimientos": datos["movimientos"],
            "total_saldos": datos["total_saldos"],
            "total_formateado": datos["total_formateado"],
            "error": error,
        },
    )


@app.get("/caja-bancos", response_class=HTMLResponse)
def mostrar_caja_bancos(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        return cargar_pagina_caja(
            request,
            token,
            empresas[0]["id"],
        )

    except Exception as error:
        print("Error al consultar caja y bancos:", repr(error))

        return HTMLResponse(
            "<h2>Error al consultar Caja y bancos</h2>"
            "<p>Revisa la terminal para conocer el problema.</p>"
            "<a href='/'>Volver al panel</a>",
            status_code=400,
        )


@app.post("/caja-bancos/cuentas")
def registrar_cuenta(
    request: Request,
    nombre: str = Form(...),
    tipo: str = Form(...),
    entidad: str = Form(""),
    saldo_inicial: float = Form(...),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        if not nombre.strip():
            raise ValueError("El nombre de la cuenta es obligatorio.")

        if tipo not in ["caja", "banco", "billetera"]:
            raise ValueError("El tipo de cuenta no es válido.")

        if saldo_inicial < 0:
            raise ValueError("El saldo inicial no puede ser negativo.")

        cliente = crear_cliente(token)
        usuario = cliente.auth.get_user(token)
        usuario_id = usuario.user.id

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        empresa_id = empresas[0]["id"]

        cliente.table("cuentas_financieras").insert({
            "usuario_id": usuario_id,
            "empresa_id": empresa_id,
            "nombre": nombre.strip(),
            "tipo": tipo,
            "entidad": entidad.strip() or None,
            "saldo_inicial": saldo_inicial,
            "activo": True,
        }).execute()

        return RedirectResponse("/caja-bancos", status_code=303)

    except Exception as error:
        print("Error al registrar cuenta:", repr(error))

        return HTMLResponse(
            "<h2>No se pudo registrar la cuenta</h2>"
            "<p>Revisa los datos y la terminal de Python.</p>"
            "<a href='/caja-bancos'>Volver</a>",
            status_code=400,
        )


@app.post("/caja-bancos/movimientos")
def registrar_movimiento(
    request: Request,
    cuenta_id: str = Form(...),
    tipo: str = Form(...),
    descripcion: str = Form(...),
    valor: float = Form(...),
    fecha: str = Form(...),
    referencia: str = Form(""),
    observaciones: str = Form(""),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        if tipo not in ["ingreso", "egreso"]:
            raise ValueError("Selecciona un tipo de movimiento válido.")

        if not descripcion.strip():
            raise ValueError("La descripción es obligatoria.")

        if valor <= 0:
            raise ValueError("El valor debe ser mayor que cero.")

        if not fecha.strip():
            raise ValueError("Selecciona la fecha del movimiento.")

        cliente = crear_cliente(token)
        usuario = cliente.auth.get_user(token)
        usuario_id = usuario.user.id

        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        empresa_id = empresas[0]["id"]

        cuenta = (
            cliente.table("cuentas_financieras")
            .select("id")
            .eq("id", cuenta_id)
            .eq("empresa_id", empresa_id)
            .eq("activo", True)
            .execute()
        )

        if not cuenta.data:
            raise ValueError(
                "La cuenta seleccionada no existe o está inactiva."
            )

        if tipo == "egreso":
            datos = cargar_datos_caja(token, empresa_id)

            saldo_cuenta = next(
                (
                    cuenta_dato["saldo_actual"]
                    for cuenta_dato in datos["cuentas"]
                    if cuenta_dato["id"] == cuenta_id
                ),
                None,
            )

            if saldo_cuenta is None:
                raise ValueError("No se pudo consultar el saldo.")

            if valor > saldo_cuenta:
                raise ValueError(
                    "No hay saldo suficiente en esta cuenta."
                )

        cliente.table("movimientos_financieros").insert({
            "usuario_id": usuario_id,
            "empresa_id": empresa_id,
            "cuenta_id": cuenta_id,
            "tipo": tipo,
            "descripcion": descripcion.strip(),
            "valor": valor,
            "fecha": fecha,
            "referencia": referencia.strip() or None,
            "observaciones": observaciones.strip() or None,
        }).execute()

        return RedirectResponse("/caja-bancos", status_code=303)

    except Exception as error:
        print("Error al registrar movimiento:", repr(error))

        return HTMLResponse(
            "<h2>No se pudo registrar el movimiento</h2>"
            "<p>Revisa los datos y la terminal de Python.</p>"
            "<a href='/caja-bancos'>Volver</a>",
            status_code=400,
        )


# =====================================================
# CONTABILIDAD BASICA
# =====================================================

def formatear_pesos(valor):
    valor = float(valor or 0)
    return "$ " + f"{valor:,.0f}".replace(",", ".")


def obtener_datos_contabilidad(token, empresa_id, desde, hasta):
    cliente = crear_cliente(token)

    consulta_ingresos = (
        cliente.table("ingresos")
        .select("fecha, descripcion, valor")
        .eq("empresa_id", empresa_id)
        .gte("fecha", desde)
        .lte("fecha", hasta)
        .execute()
    )

    consulta_gastos = (
        cliente.table("gastos")
        .select("fecha, descripcion, valor")
        .eq("empresa_id", empresa_id)
        .gte("fecha", desde)
        .lte("fecha", hasta)
        .execute()
    )

    ingresos = consulta_ingresos.data or []
    gastos = consulta_gastos.data or []

    total_ingresos = sum(
        float(registro.get("valor") or 0)
        for registro in ingresos
    )

    total_gastos = sum(
        float(registro.get("valor") or 0)
        for registro in gastos
    )

    resultado = total_ingresos - total_gastos

    movimientos = []

    for registro in ingresos:
        movimientos.append({
            "fecha": registro.get("fecha"),
            "tipo": "ingreso",
            "descripcion": registro.get("descripcion") or "Ingreso",
            "valor": float(registro.get("valor") or 0),
        })

    for registro in gastos:
        movimientos.append({
            "fecha": registro.get("fecha"),
            "tipo": "gasto",
            "descripcion": registro.get("descripcion") or "Gasto",
            "valor": float(registro.get("valor") or 0),
        })

    movimientos.sort(
        key=lambda movimiento: str(movimiento["fecha"] or ""),
        reverse=True,
    )

    return {
        "resumen": {
            "ingresos": formatear_pesos(total_ingresos),
            "gastos": formatear_pesos(total_gastos),
            "ganancia": formatear_pesos(resultado),
            "operaciones": len(movimientos),
        },
        "movimientos": movimientos,
    }


@app.get("/contabilidad", response_class=HTMLResponse)
def mostrar_contabilidad(
    request: Request,
    desde: str = "",
    hasta: str = "",
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        hoy = date.today()

        if not desde:
            desde = hoy.replace(day=1).isoformat()

        if not hasta:
            hasta = hoy.isoformat()

        fecha_desde = date.fromisoformat(desde)
        fecha_hasta = date.fromisoformat(hasta)

        if fecha_desde > fecha_hasta:
            raise ValueError(
                "La fecha inicial no puede ser posterior a la final."
            )

        datos = obtener_datos_contabilidad(
            token,
            empresas[0]["id"],
            desde,
            hasta,
        )

        return templates.TemplateResponse(
            request=request,
            name="contabilidad.html",
            context={
                "resumen": datos["resumen"],
                "movimientos": datos["movimientos"],
                "desde": desde,
                "hasta": hasta,
            },
        )

    except Exception as error:
        print("Error al consultar contabilidad:", repr(error))

        return HTMLResponse(
            "<h2>Error al consultar contabilidad</h2>"
            "<p>Revisa la terminal de Python para conocer el problema.</p>"
            "<a href='/'>Volver al panel</a>",
            status_code=400,
        )


# =====================================================
# INFORMES
# =====================================================

def obtener_datos_informes(token, empresa_id, desde, hasta):
    cliente = crear_cliente(token)

    consulta_ventas = (
        cliente.table("ingresos")
        .select("fecha, descripcion, valor")
        .eq("empresa_id", empresa_id)
        .gte("fecha", desde)
        .lte("fecha", hasta)
        .order("fecha", desc=True)
        .execute()
    )

    consulta_gastos = (
        cliente.table("gastos")
        .select("fecha, descripcion, valor")
        .eq("empresa_id", empresa_id)
        .gte("fecha", desde)
        .lte("fecha", hasta)
        .order("fecha", desc=True)
        .execute()
    )

    consulta_inventario = (
        cliente.table("productos")
        .select(
            "id, nombre, codigo, stock, stock_minimo, "
            "precio_compra, precio_venta, activo"
        )
        .eq("empresa_id", empresa_id)
        .eq("activo", True)
        .order("nombre")
        .execute()
    )

    ventas = consulta_ventas.data or []
    gastos = consulta_gastos.data or []
    productos = consulta_inventario.data or []

    total_ventas = sum(
        float(registro.get("valor") or 0)
        for registro in ventas
    )

    total_gastos = sum(
        float(registro.get("valor") or 0)
        for registro in gastos
    )

    ganancia = total_ventas - total_gastos

    stock_bajo = [
        producto for producto in productos
        if float(producto.get("stock") or 0)
        <= float(producto.get("stock_minimo") or 0)
    ]

    resumen = {
        "ventas": formatear_pesos(total_ventas),
        "gastos": formatear_pesos(total_gastos),
        "ganancia": formatear_pesos(ganancia),
        "operaciones": len(ventas) + len(gastos),
    }

    return {
        "resumen": resumen,
        "productos": productos,
        "stock_bajo": stock_bajo,
    }


@app.get("/informes", response_class=HTMLResponse)
def mostrar_informes(
    request: Request,
    desde: str = "",
    hasta: str = "",
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresas = buscar_empresa(token)

        if not empresas:
            return RedirectResponse("/empresa", status_code=303)

        hoy = date.today()

        if not desde:
            desde = hoy.replace(day=1).isoformat()

        if not hasta:
            hasta = hoy.isoformat()

        fecha_desde = date.fromisoformat(desde)
        fecha_hasta = date.fromisoformat(hasta)

        if fecha_desde > fecha_hasta:
            raise ValueError(
                "La fecha inicial no puede ser posterior a la final."
            )

        datos = obtener_datos_informes(
            token,
            empresas[0]["id"],
            desde,
            hasta,
        )

        return templates.TemplateResponse(
            request=request,
            name="informes.html",
            context={
                "resumen": datos["resumen"],
                "productos": datos["productos"],
                "stock_bajo": datos["stock_bajo"],
                "desde": desde,
                "hasta": hasta,
            },
        )

    except Exception as error:
        print("Error al consultar Informes:", repr(error))

        return HTMLResponse(
            "<h2>Error al consultar Informes</h2>"
            "<p>Revisa la terminal para conocer el problema.</p>"
            "<a href='/'>Volver al panel</a>",
            status_code=400,
        )
