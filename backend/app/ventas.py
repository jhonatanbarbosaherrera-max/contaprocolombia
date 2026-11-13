from datetime import date
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.app.database.supabase_client import crear_cliente


router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

templates = Jinja2Templates(
    directory=str(FRONTEND_DIR / "templates")
)


def obtener_empresa(token):
    cliente = crear_cliente(token)
    cliente.auth.get_user(token)

    resultado = (
        cliente.table("empresas")
        .select("id, nombre")
        .limit(1)
        .execute()
    )

    if not resultado.data:
        return None

    return resultado.data[0]


def obtener_cuentas(token, empresa_id):
    cliente = crear_cliente(token)

    resultado = (
        cliente.table("cuentas_financieras")
        .select("id, nombre, tipo")
        .eq("empresa_id", empresa_id)
        .eq("activo", True)
        .order("created_at", desc=True)
        .execute()
    )

    return resultado.data or []


def obtener_productos_venta(token, empresa_id):
    cliente = crear_cliente(token)

    resultado = (
        cliente.table("productos")
        .select("id, nombre, codigo, precio_venta, stock")
        .eq("empresa_id", empresa_id)
        .eq("activo", True)
        .gt("stock", 0)
        .order("nombre")
        .execute()
    )

    return resultado.data or []


def cargar_ventas(request, token, empresa_id, error=None, guardada=False):
    cuentas = obtener_cuentas(token, empresa_id)
    productos = obtener_productos_venta(token, empresa_id)

    return templates.TemplateResponse(
        request=request,
        name="ventas.html",
        context={
            "cuentas": cuentas,
            "productos": productos,
            "fecha": date.today().isoformat(),
            "error": error,
            "guardada": guardada,
        },
    )


@router.get("/ventas", response_class=HTMLResponse)
def mostrar_ventas(request: Request, guardada: int = 0):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    try:
        empresa = obtener_empresa(token)

        if not empresa:
            return RedirectResponse("/empresa", status_code=303)

        return cargar_ventas(
            request,
            token,
            empresa["id"],
            guardada=bool(guardada),
        )

    except Exception as error:
        print("Error al cargar ventas:", repr(error))

        return HTMLResponse(
            "<h2>Error al cargar Ventas</h2>"
            "<p>Revisa la terminal de Python.</p>"
            "<a href='/'>Volver al panel</a>",
            status_code=400,
        )


@router.get("/ventas/buscar-cliente")
def buscar_cliente_venta(request: Request, documento: str = ""):
    token = request.cookies.get("access_token")

    if not token:
        return JSONResponse(
            {"error": "La sesión ha expirado. Inicia sesión nuevamente."},
            status_code=401,
        )

    documento = documento.strip()

    if not documento:
        return JSONResponse(
            {"error": "Escribe el número de identificación."},
            status_code=400,
        )

    try:
        empresa = obtener_empresa(token)

        if not empresa:
            return JSONResponse(
                {"error": "No se encontró una empresa registrada."},
                status_code=400,
            )

        cliente = crear_cliente(token)

        resultado = (
            cliente.table("clientes")
            .select(
                "id, nombre, documento, telefono, correo, direccion"
            )
            .eq("empresa_id", empresa["id"])
            .eq("documento", documento)
            .limit(1)
            .execute()
        )

        if resultado.data:
            return JSONResponse({
                "encontrado": True,
                "cliente": resultado.data[0],
            })

        return JSONResponse({
            "encontrado": False,
            "cliente": None,
        })

    except Exception as error:
        print("Error al buscar cliente:", repr(error))

        return JSONResponse(
            {"error": "No se pudo consultar el cliente."},
            status_code=400,
        )


@router.post("/ventas", response_class=HTMLResponse)
def registrar_venta(
    request: Request,
    cliente_documento: str = Form(...),
    cliente_nombre: str = Form(""),
    cliente_telefono: str = Form(""),
    cliente_correo: str = Form(""),
    cliente_direccion: str = Form(""),
    producto_id: list[str] = Form(...),
    cantidad: list[int] = Form(...),
    fecha: str = Form(...),
    metodo_pago: str = Form(...),
    cuenta_id: str = Form(...),
):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login", status_code=303)

    empresa_id = None

    try:
        documento = cliente_documento.strip()
        nombre = cliente_nombre.strip()

        if not documento:
            raise ValueError(
                "Debes escribir la identificación del cliente."
            )

        if not fecha.strip():
            raise ValueError("Selecciona la fecha de la venta.")

        if metodo_pago not in [
            "Efectivo",
            "Transferencia",
            "Tarjeta",
            "Otro",
        ]:
            raise ValueError("Selecciona un método de pago válido.")

        if not producto_id or len(producto_id) != len(cantidad):
            raise ValueError(
                "Agrega al menos un producto y verifica sus cantidades."
            )

        empresa = obtener_empresa(token)

        if not empresa:
            return RedirectResponse("/empresa", status_code=303)

        empresa_id = empresa["id"]

        cliente = crear_cliente(token)
        usuario = cliente.auth.get_user(token)
        usuario_id = usuario.user.id

        # Validar la cuenta seleccionada.
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

        # Agrupar productos repetidos y validar existencias.
        cantidades = {}

        for identificador, unidades in zip(producto_id, cantidad):
            if not identificador:
                raise ValueError("Selecciona todos los productos.")

            unidades = int(unidades)

            if unidades <= 0:
                raise ValueError(
                    "La cantidad de cada producto debe ser mayor que cero."
                )

            cantidades[identificador] = (
                cantidades.get(identificador, 0) + unidades
            )

        items = []

        for identificador, unidades in cantidades.items():
            producto = (
                cliente.table("productos")
                .select("id, nombre, precio_venta, stock")
                .eq("id", identificador)
                .eq("empresa_id", empresa_id)
                .eq("activo", True)
                .execute()
            )

            if not producto.data:
                raise ValueError(
                    "Uno de los productos ya no está disponible."
                )

            datos_producto = producto.data[0]
            stock = int(datos_producto.get("stock") or 0)
            precio = float(datos_producto.get("precio_venta") or 0)

            if unidades > stock:
                raise ValueError(
                    "No hay existencias suficientes de "
                    + datos_producto["nombre"]
                    + ". Disponibles: "
                    + str(stock)
                )

            if precio <= 0:
                raise ValueError(
                    "El producto "
                    + datos_producto["nombre"]
                    + " no tiene un precio de venta válido."
                )

            items.append({
                "producto_id": identificador,
                "cantidad": unidades,
            })

        # Buscar al cliente por su identificación.
        resultado_cliente = (
            cliente.table("clientes")
            .select("id")
            .eq("empresa_id", empresa_id)
            .eq("documento", documento)
            .limit(1)
            .execute()
        )

        if resultado_cliente.data:
            cliente_id = resultado_cliente.data[0]["id"]

        else:
            if not nombre:
                raise ValueError(
                    "El cliente no está registrado. "
                    "Escribe su nombre para registrarlo."
                )

            nuevo_cliente = (
                cliente.table("clientes")
                .insert({
                    "usuario_id": usuario_id,
                    "empresa_id": empresa_id,
                    "nombre": nombre,
                    "documento": documento,
                    "telefono": cliente_telefono.strip() or None,
                    "correo": cliente_correo.strip() or None,
                    "direccion": cliente_direccion.strip() or None,
                })
                .execute()
            )

            if not nuevo_cliente.data:
                raise ValueError(
                    "No se pudo registrar el nuevo cliente."
                )

            cliente_id = nuevo_cliente.data[0]["id"]

        # Registrar venta, detalle, descuento de inventario e ingreso
        # mediante la función RPC creada previamente en Supabase.
        resultado = cliente.rpc(
            "registrar_venta_completa",
            {
                "p_usuario_id": usuario_id,
                "p_empresa_id": empresa_id,
                "p_cliente_id": cliente_id,
                "p_cuenta_id": cuenta_id,
                "p_fecha": fecha,
                "p_metodo_pago": metodo_pago,
                "p_items": items,
            },
        ).execute()

        if resultado.data is None:
            raise ValueError(
                "Supabase no confirmó el registro de la venta."
            )

        return RedirectResponse(
            "/ventas?guardada=1",
            status_code=303,
        )

    except Exception as error:
        print("ERROR AL REGISTRAR VENTA:", repr(error))

        try:
            if empresa_id:
                return cargar_ventas(
                    request,
                    token,
                    empresa_id,
                    error=str(error),
                )
        except Exception as error_pagina:
            print(
                "Error al volver a cargar Ventas:",
                repr(error_pagina),
            )

        return HTMLResponse(
            "<h2>No se pudo registrar la venta</h2>"
            "<p>Revisa la terminal de Python para conocer el error.</p>"
            "<a href='/ventas'>Volver a Ventas</a>",
            status_code=400,
        )