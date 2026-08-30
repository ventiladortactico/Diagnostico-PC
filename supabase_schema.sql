-- OptiChek: Esquema Supabase (ejecutar en el SQL Editor)
-- Tabla de tecnicos registrados
create table if not exists public.tecnicos (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  nombre text not null,
  whatsapp text default '',
  logo_url text default '',
  color text default '#2563eb',
  creado_en timestamptz default now()
);

-- Tabla de suscripciones (una por tecnico, la vigente gobierna el modo tecnico)
create table if not exists public.suscripciones (
  id uuid primary key default gen_random_uuid(),
  tecnico_id uuid references public.tecnicos(id) on delete cascade not null,
  vence date not null,
  estado text not null default 'activa' check (estado in ('activa','renovada','cancelada','vencida')),
  creado_en timestamptz default now()
);

-- Tabla de claves de activacion (canjeables por +365 dias de modo tecnico)
create table if not exists public.claves_activacion (
  clave text primary key,
  creada_para text not null,          -- nombre/email del tecnico
  dias integer not null default 365,  -- duracion que otorga
  canjeada boolean not null default false,
  canjeada_por uuid references public.tecnicos(id),
  canjeada_en timestamptz,
  creada_en timestamptz default now()
);

-- Tabla de sesiones: una fila por tecnico. Quien loguea por ultima vez toma la sesion activa.
create table if not exists public.sessions (
  tecnico_id uuid primary key references public.tecnicos(id) on delete cascade,
  session_id text not null,
  ultima_actividad timestamptz default now()
);

-- RLS para sessions (el tecnico solo ve su propia fila)
alter table public.sessions enable row level security;
create policy "sessions_select_own" on public.sessions
  for select using (tecnico_id = (select auth.uid()));
create policy "sessions_upsert_own" on public.sessions
  for all using (tecnico_id = (select auth.uid()))
  with check (tecnico_id = (select auth.uid()));

-- Indices utiles
create index if not exists idx_suscripciones_tecnico on public.suscripciones(tecnico_id, vence desc);

-- Iniciar sesion: reemplaza la fila activa (el ultimo login gana).
create or replace function public.iniciar_sesion(p_session_id text)
returns jsonb
security definer
set search_path = public
as $$
declare
  v_id uuid := (select auth.uid());
begin
  if v_id is null then
    raise exception 'NO_AUTENTICADO';
  end if;
  insert into public.sessions (tecnico_id, session_id, ultima_actividad)
  values (v_id, p_session_id, now())
  on conflict (tecnico_id)
  do update set session_id = excluded.session_id, ultima_actividad = now();
  return jsonb_build_object('activa', true);
end;
$$ language plpgsql;

-- Verificar sesion: dice si los ids coinciden (la app corta la sesion local si no).
create or replace function public.verificar_sesion(p_session_id text)
returns jsonb
security definer
set search_path = public
as $$
declare
  v_id uuid := (select auth.uid());
  v_activa boolean;
begin
  if v_id is null then
    raise exception 'NO_AUTENTICADO';
  end if;
  select (s.session_id = p_session_id) into v_activa
  from public.sessions s
  where s.tecnico_id = v_id;
  v_activa := coalesce(v_activa, false);
  update public.sessions set ultima_actividad = now()
  where tecnico_id = v_id and session_id = p_session_id;
  return jsonb_build_object('activa', v_activa);
end;
$$ language plpgsql;

grant execute on function public.iniciar_sesion(p_session_id text) to anon, authenticated;
grant execute on function public.verificar_sesion(p_session_id text) to anon, authenticated;

-- RLS: cada tecnico solo ve/edita su propia fila
alter table public.tecnicos enable row level security;
alter table public.suscripciones enable row level security;

create policy "tecnicos_select_own" on public.tecnicos
  for select using ((select auth.uid()) = id);
create policy "tecnicos_update_own" on public.tecnicos
  for update using ((select auth.uid()) = id);
create policy "suscripciones_select_own" on public.suscripciones
  for select using (tecnico_id = (select auth.uid()));
create policy "suscripciones_insert_own" on public.suscripciones
  for insert with check (tecnico_id = (select auth.uid()));

-- La creacion de una clave NO la hace el tecnico; la generas vos (creador).
-- RLS: el tecnico solo puede CANJEAR (update limitado) una clave no usada; no leer el lote.
create policy "claves_canje_select_own" on public.claves_activacion
  for select using (canjeada_por = (select auth.uid()));
create policy "claves_canje_update" on public.claves_activacion
  for update using (true)
  with check (canjeada_por = (select auth.uid()));

-- Funcion PL/pgSQL canjeable via RPC: valida, marca usada y crea/renueva suscripcion.
create or replace function public.canjear_clave(p_clave text)
returns jsonb
security definer
set search_path = public
as $$
declare
  v_dias integer;
  v_tecnico_id uuid := (select auth.uid());
  v_actual date;
  v_nueva date;
begin
  if v_tecnico_id is null then
    raise exception 'NO_AUTENTICADO';
  end if;

  select dias into v_dias from public.claves_activacion
  where clave = p_clave and canjeada = false
  for update;

  if v_dias is null then
    raise exception 'CLAVE_INVALIDA_O_USADA';
  end if;

  update public.claves_activacion
  set canjeada = true, canjeada_por = v_tecnico_id, canjeada_en = now()
  where clave = p_clave;

  select vence into v_actual from public.suscripciones
  where tecnico_id = v_tecnico_id order by vence desc limit 1;

  v_nueva := coalesce(v_actual, current_date) + v_dias;

  insert into public.suscripciones (tecnico_id, vence, estado)
  values (v_tecnico_id, v_nueva, 'renovada');

  return jsonb_build_object('nueva_vence', to_char(v_nueva, 'DD/MM/YYYY'));
end;
$$ language plpgsql;

revoke all on function public.canjear_clave(p_clave text) from public;
grant execute on function public.canjear_clave(p_clave text) to anon, authenticated;

-- Registro automatico: al crear la cuenta (auth.users), se crea la fila del tecnico.
create or replace function public.handle_tecnico_registro()
returns trigger
security definer
set search_path = public
as $$
begin
  insert into public.tecnicos (id, email, nombre)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'nombre', 'Tecnico'))
  on conflict (id) do nothing;
  return new;
end;
$$ language plpgsql;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_tecnico_registro();

-- (Paso 2, por pago) RPC llamada por la funcion de pago: extiende la suscripcion +dias desde hoy
-- o desde el vencimiento vigente (lo que sea mayor). Ejecutada con service role desde la Edge Function.
create or replace function public.renovar_por_pago(p_tecnico_id uuid, p_dias integer)
returns jsonb
security definer
set search_path = public
as $$
declare
  v_actual date;
  v_nueva date;
begin
  select vence into v_actual from public.suscripciones
  where tecnico_id = p_tecnico_id order by vence desc limit 1;
  v_nueva := greatest(coalesce(v_actual, current_date), current_date) + p_dias;
  insert into public.suscripciones (tecnico_id, vence, estado)
  values (p_tecnico_id, v_nueva, 'renovada');
  return jsonb_build_object('vence', to_char(v_nueva, 'YYYY-MM-DD'));
end;
$$ language plpgsql;

revoke all on function public.renovar_por_pago(p_tecnico_id uuid, p_dias integer) from public;
grant execute on function public.renovar_por_pago(p_tecnico_id uuid, p_dias integer) to service_role;