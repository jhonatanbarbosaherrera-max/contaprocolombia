-- ContaPro Colombia - esquema inicial para el proyecto Supabase nuevo
-- Ejecutar completo en Supabase > SQL Editor > New query.
-- Requiere autenticación Supabase Auth. No usa service_role ni buckets.

create extension if not exists pgcrypto;

-- 1. Empresas y datos maestros
create table if not exists public.empresas (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    nombre varchar(150) not null,
    nit varchar(50),
    telefono varchar(30),
    correo varchar(150),
    direccion text,
    created_at timestamptz not null default now()
);

create table if not exists public.clientes (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    nombre varchar(150) not null,
    documento varchar(50),
    telefono varchar(30),
    correo varchar(150),
    direccion text,
    created_at timestamptz not null default now()
);

create table if not exists public.proveedores (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    nombre varchar(150) not null,
    documento varchar(50),
    telefono varchar(30),
    correo varchar(150),
    direccion text,
    created_at timestamptz not null default now()
);

create table if not exists public.cuentas_financieras (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    nombre varchar(120) not null,
    tipo varchar(20) not null check (tipo in ('caja','banco','billetera')),
    entidad varchar(120),
    saldo_inicial numeric(14,2) not null default 0 check (saldo_inicial >= 0),
    activo boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists public.productos (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    nombre varchar(150) not null,
    codigo varchar(80),
    descripcion text,
    precio_compra numeric(14,2) not null default 0 check (precio_compra >= 0),
    precio_venta numeric(14,2) not null default 0 check (precio_venta >= 0),
    stock numeric(14,2) not null default 0 check (stock >= 0),
    stock_minimo numeric(14,2) not null default 0 check (stock_minimo >= 0),
    activo boolean not null default true,
    created_at timestamptz not null default now()
);

-- 2. Operaciones de compra
create table if not exists public.compras (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    proveedor_id uuid references public.proveedores(id) on delete set null,
    cuenta_id uuid references public.cuentas_financieras(id) on delete set null,
    fecha date not null default current_date,
    descripcion text,
    metodo_pago varchar(30),
    total numeric(14,2) not null default 0 check (total >= 0),
    created_at timestamptz not null default now()
);

create table if not exists public.detalle_compras (
    id uuid primary key default gen_random_uuid(),
    compra_id uuid not null references public.compras(id) on delete cascade,
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    producto_id uuid not null references public.productos(id) on delete restrict,
    cantidad numeric(14,2) not null check (cantidad > 0),
    precio_unitario numeric(14,2) not null check (precio_unitario > 0),
    subtotal numeric(14,2) not null check (subtotal >= 0),
    created_at timestamptz not null default now()
);

-- 3. Ventas y detalle de venta
create table if not exists public.ventas (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    cliente_id uuid references public.clientes(id) on delete set null,
    cuenta_id uuid references public.cuentas_financieras(id) on delete set null,
    fecha date not null default current_date,
    metodo_pago varchar(30),
    total numeric(14,2) not null default 0 check (total >= 0),
    created_at timestamptz not null default now()
);

create table if not exists public.detalle_ventas (
    id uuid primary key default gen_random_uuid(),
    venta_id uuid not null references public.ventas(id) on delete cascade,
    producto_id uuid not null references public.productos(id) on delete restrict,
    cantidad numeric(14,2) not null check (cantidad > 0),
    precio_unitario numeric(14,2) not null check (precio_unitario >= 0),
    subtotal numeric(14,2) not null check (subtotal >= 0),
    created_at timestamptz not null default now()
);

-- 4. Caja, ingresos, gastos y movimientos
create table if not exists public.ingresos (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    cliente_id uuid references public.clientes(id) on delete set null,
    descripcion text not null,
    valor numeric(14,2) not null check (valor > 0),
    fecha date default current_date,
    metodo_pago varchar(30),
    referencia varchar(120),
    observaciones text,
    cuenta_id uuid references public.cuentas_financieras(id) on delete set null,
    created_at timestamptz not null default now()
);

create table if not exists public.gastos (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    proveedor_id uuid references public.proveedores(id) on delete set null,
    descripcion text not null,
    valor numeric(14,2) not null check (valor > 0),
    fecha date default current_date,
    metodo_pago varchar(30),
    referencia varchar(120),
    observaciones text,
    cuenta_id uuid references public.cuentas_financieras(id) on delete set null,
    created_at timestamptz not null default now()
);

create table if not exists public.movimientos_financieros (
    id uuid primary key default gen_random_uuid(),
    usuario_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    cuenta_id uuid not null references public.cuentas_financieras(id) on delete restrict,
    tipo varchar(20) not null check (tipo in ('ingreso','egreso')),
    descripcion text not null,
    valor numeric(14,2) not null check (valor > 0),
    fecha date not null default current_date,
    referencia varchar(120),
    observaciones text,
    created_at timestamptz not null default now()
);

-- 5. Índices para filtros habituales del backend
create index if not exists idx_empresas_usuario on public.empresas(usuario_id);
create index if not exists idx_clientes_empresa on public.clientes(empresa_id);
create index if not exists idx_proveedores_empresa on public.proveedores(empresa_id);
create index if not exists idx_productos_empresa on public.productos(empresa_id);
create index if not exists idx_compras_empresa_fecha on public.compras(empresa_id, fecha desc);
create index if not exists idx_detalle_compras_compra on public.detalle_compras(compra_id);
create index if not exists idx_ventas_empresa_fecha on public.ventas(empresa_id, fecha desc);
create index if not exists idx_detalle_ventas_venta on public.detalle_ventas(venta_id);
create index if not exists idx_ingresos_empresa_fecha on public.ingresos(empresa_id, fecha desc);
create index if not exists idx_gastos_empresa_fecha on public.gastos(empresa_id, fecha desc);
create index if not exists idx_cuentas_empresa on public.cuentas_financieras(empresa_id);
create index if not exists idx_movimientos_empresa_fecha on public.movimientos_financieros(empresa_id, fecha desc);

-- 6. RLS: una cuenta solo accede a empresas propias y a sus registros.
alter table public.empresas enable row level security;
alter table public.clientes enable row level security;
alter table public.proveedores enable row level security;
alter table public.cuentas_financieras enable row level security;
alter table public.productos enable row level security;
alter table public.compras enable row level security;
alter table public.detalle_compras enable row level security;
alter table public.ventas enable row level security;
alter table public.detalle_ventas enable row level security;
alter table public.ingresos enable row level security;
alter table public.gastos enable row level security;
alter table public.movimientos_financieros enable row level security;

drop policy if exists empresas_propias on public.empresas;
create policy empresas_propias on public.empresas
for all to authenticated
using (usuario_id = (select auth.uid()))
with check (usuario_id = (select auth.uid()));

-- Tablas con empresa_id y usuario_id
do $$
declare t text;
begin
  foreach t in array array[
    'clientes','proveedores','cuentas_financieras','productos',
    'compras','detalle_compras','ventas','ingresos','gastos',
    'movimientos_financieros'
  ] loop
    execute format('drop policy if exists %I on public.%I', t || '_propios', t);
    execute format(
      'create policy %I on public.%I for all to authenticated using
       (usuario_id = (select auth.uid()) and exists
        (select 1 from public.empresas e where e.id = empresa_id and e.usuario_id = (select auth.uid())))
       with check
       (usuario_id = (select auth.uid()) and exists
        (select 1 from public.empresas e where e.id = empresa_id and e.usuario_id = (select auth.uid())))',
      t || '_propios', t
    );
  end loop;
end $$;

-- detalle_ventas no tiene usuario_id/empresa_id: se autoriza a través de su venta.
drop policy if exists detalle_ventas_propios on public.detalle_ventas;
create policy detalle_ventas_propios on public.detalle_ventas
for all to authenticated
using (
  exists (
    select 1 from public.ventas v
    join public.empresas e on e.id = v.empresa_id
    where v.id = venta_id
      and v.usuario_id = (select auth.uid())
      and e.usuario_id = (select auth.uid())
  )
)
with check (
  exists (
    select 1 from public.ventas v
    join public.empresas e on e.id = v.empresa_id
    where v.id = venta_id
      and v.usuario_id = (select auth.uid())
      and e.usuario_id = (select auth.uid())
  )
);

-- 7. RPC transaccional requerida por backend/app/ventas.py
create or replace function public.registrar_venta_completa(
    p_usuario_id uuid,
    p_empresa_id uuid,
    p_cliente_id uuid,
    p_cuenta_id uuid,
    p_fecha date,
    p_metodo_pago text,
    p_items jsonb
)
returns uuid
language plpgsql
set search_path = ''
as $$
declare
    v_venta_id uuid;
    v_producto_id uuid;
    v_cantidad numeric(14,2);
    v_precio numeric(14,2);
    v_stock numeric(14,2);
    v_total numeric(14,2) := 0;
    v_item jsonb;
begin
    if auth.uid() is null or auth.uid() <> p_usuario_id then
        raise exception 'Usuario no autorizado.';
    end if;

    if not exists (
        select 1 from public.empresas e
        where e.id = p_empresa_id and e.usuario_id = auth.uid()
    ) then
        raise exception 'La empresa no pertenece al usuario.';
    end if;

    if p_items is null or jsonb_typeof(p_items) <> 'array'
       or jsonb_array_length(p_items) = 0 then
        raise exception 'La venta debe contener al menos un producto.';
    end if;

    if not exists (
        select 1 from public.cuentas_financieras c
        where c.id = p_cuenta_id and c.empresa_id = p_empresa_id
          and c.usuario_id = auth.uid() and c.activo = true
    ) then
        raise exception 'La cuenta no existe o está inactiva.';
    end if;

    if p_cliente_id is not null and not exists (
        select 1 from public.clientes c
        where c.id = p_cliente_id and c.empresa_id = p_empresa_id
          and c.usuario_id = auth.uid()
    ) then
        raise exception 'El cliente no pertenece a la empresa.';
    end if;

    insert into public.ventas(usuario_id, empresa_id, cliente_id, cuenta_id, fecha, metodo_pago, total)
    values (p_usuario_id, p_empresa_id, p_cliente_id, p_cuenta_id, coalesce(p_fecha, current_date), p_metodo_pago, 0)
    returning id into v_venta_id;

    for v_item in select value from jsonb_array_elements(p_items)
    loop
        v_producto_id := (v_item->>'producto_id')::uuid;
        v_cantidad := (v_item->>'cantidad')::numeric;

        if v_cantidad is null or v_cantidad <= 0 then
            raise exception 'La cantidad debe ser mayor que cero.';
        end if;

        select p.stock, p.precio_venta
          into v_stock, v_precio
        from public.productos p
        where p.id = v_producto_id
          and p.empresa_id = p_empresa_id
          and p.usuario_id = auth.uid()
          and p.activo = true
        for update;

        if not found then
            raise exception 'Producto no encontrado o inactivo: %', v_producto_id;
        end if;

        if v_stock < v_cantidad then
            raise exception 'Stock insuficiente para el producto %.', v_producto_id;
        end if;

        if v_precio is null or v_precio <= 0 then
            raise exception 'El producto no tiene precio de venta válido.';
        end if;

        insert into public.detalle_ventas(venta_id, producto_id, cantidad, precio_unitario, subtotal)
        values (v_venta_id, v_producto_id, v_cantidad, v_precio, v_cantidad * v_precio);

        update public.productos
        set stock = stock - v_cantidad
        where id = v_producto_id and empresa_id = p_empresa_id;

        v_total := v_total + (v_cantidad * v_precio);
    end loop;

    update public.ventas set total = v_total where id = v_venta_id;

    insert into public.ingresos(
        usuario_id, empresa_id, cliente_id, cuenta_id,
        descripcion, valor, fecha, metodo_pago, referencia
    )
    values (
        p_usuario_id, p_empresa_id, p_cliente_id, p_cuenta_id,
        'Venta ' || v_venta_id::text, v_total, coalesce(p_fecha, current_date),
        p_metodo_pago, v_venta_id::text
    );

    return v_venta_id;
end;
$$;

revoke all on function public.registrar_venta_completa(uuid,uuid,uuid,uuid,date,text,jsonb) from public;
grant execute on function public.registrar_venta_completa(uuid,uuid,uuid,uuid,date,text,jsonb) to authenticated;

-- 8. Permisos API para usuarios autenticados; RLS sigue siendo obligatoria.
grant usage on schema public to authenticated;
grant select, insert, update, delete on
  public.empresas, public.clientes, public.proveedores,
  public.cuentas_financieras, public.productos, public.compras,
  public.detalle_compras, public.ventas, public.detalle_ventas,
  public.ingresos, public.gastos, public.movimientos_financieros
to authenticated;

-- No se crean buckets: el código revisado no utiliza Supabase Storage.
