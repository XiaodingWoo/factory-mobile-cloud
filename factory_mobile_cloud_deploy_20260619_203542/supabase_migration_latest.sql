begin;

create extension if not exists pgcrypto;

create table if not exists public.stock_in_requests (
    id uuid primary key default gen_random_uuid(),
    client_request_id text unique,
    product_code text,
    product_name varchar(240) not null,
    qty numeric not null check (qty > 0 and qty = floor(qty)),
    operator_name varchar(120),
    note varchar(1000),
    machine_id text,
    schedule_id text,
    mould_number text,
    production_status text,
    pallet_qty numeric,
    quantity_mode text default 'custom',
    request_type text default 'stock_in',
    loose_status text,
    source varchar(40) default 'mobile',
    status varchar(20) not null default 'pending',
    processed_at timestamptz,
    error_message text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Existing RLS policies may depend on product_code or other columns.
-- Drop them before type/constraint changes, then recreate them below.
drop policy if exists "mobile insert stock in requests" on public.stock_in_requests;

alter table public.stock_in_requests add column if not exists client_request_id text;
alter table public.stock_in_requests add column if not exists product_code text;
alter table public.stock_in_requests alter column product_code type text;
alter table public.stock_in_requests add column if not exists product_name varchar(240);
alter table public.stock_in_requests add column if not exists qty numeric;
alter table public.stock_in_requests add column if not exists operator_name varchar(120);
alter table public.stock_in_requests add column if not exists note varchar(1000);
alter table public.stock_in_requests add column if not exists machine_id text;
alter table public.stock_in_requests add column if not exists schedule_id text;
alter table public.stock_in_requests add column if not exists mould_number text;
alter table public.stock_in_requests add column if not exists production_status text;
alter table public.stock_in_requests add column if not exists pallet_qty numeric;
alter table public.stock_in_requests add column if not exists quantity_mode text default 'custom';
alter table public.stock_in_requests add column if not exists request_type text default 'stock_in';
alter table public.stock_in_requests add column if not exists loose_status text;
alter table public.stock_in_requests add column if not exists source varchar(40) default 'mobile';
alter table public.stock_in_requests add column if not exists status varchar(20) default 'pending';
alter table public.stock_in_requests add column if not exists processed_at timestamptz;
alter table public.stock_in_requests add column if not exists error_message text;
alter table public.stock_in_requests add column if not exists created_at timestamptz default now();
alter table public.stock_in_requests add column if not exists updated_at timestamptz default now();

update public.stock_in_requests
set client_request_id = coalesce(nullif(client_request_id, ''), id::text),
    product_name = left(coalesce(nullif(product_name, ''), product_code, 'Unknown product'), 240),
    product_code = nullif(coalesce(product_code, ''), ''),
    operator_name = nullif(left(coalesce(operator_name, ''), 120), ''),
    note = nullif(left(coalesce(note, ''), 1000), ''),
    quantity_mode = coalesce(nullif(quantity_mode, ''), 'custom'),
    request_type = coalesce(nullif(request_type, ''), nullif(quantity_mode, ''), 'stock_in'),
    source = coalesce(nullif(source, ''), 'mobile'),
    status = coalesce(nullif(status, ''), 'pending'),
    updated_at = coalesce(updated_at, now());

create unique index if not exists stock_in_requests_client_request_id_key
on public.stock_in_requests (client_request_id);

alter table public.stock_in_requests
    alter column client_request_id set not null,
    alter column product_name set not null,
    alter column status set default 'pending',
    alter column status set not null;

alter table public.stock_in_requests
    drop constraint if exists stock_in_requests_status_check;
alter table public.stock_in_requests
    add constraint stock_in_requests_status_check
    check (status in ('pending', 'processing', 'processed', 'error'));

alter table public.stock_in_requests
    drop constraint if exists stock_in_requests_qty_check;
alter table public.stock_in_requests
    add constraint stock_in_requests_qty_check
    check (qty > 0 and qty = floor(qty));

create table if not exists public.mobile_public_products (
    id uuid primary key default gen_random_uuid(),
    product_code text,
    product_name varchar(240) not null,
    label varchar(120),
    pallet_qty numeric,
    search_text text,
    is_active boolean default true,
    updated_at timestamptz default now()
);

drop policy if exists "mobile read active products" on public.mobile_public_products;

alter table public.mobile_public_products add column if not exists product_code text;
alter table public.mobile_public_products alter column product_code type text;
alter table public.mobile_public_products add column if not exists product_name varchar(240);
alter table public.mobile_public_products add column if not exists label varchar(120);
alter table public.mobile_public_products add column if not exists pallet_qty numeric;
alter table public.mobile_public_products add column if not exists search_text text;
alter table public.mobile_public_products add column if not exists is_active boolean default true;
alter table public.mobile_public_products add column if not exists updated_at timestamptz default now();

update public.mobile_public_products
set product_code = coalesce(nullif(product_code, ''), product_name, id::text),
    product_name = left(coalesce(nullif(product_name, ''), product_code, id::text), 240),
    label = nullif(left(coalesce(label, ''), 120), ''),
    is_active = coalesce(is_active, true),
    updated_at = coalesce(updated_at, now());

drop index if exists public.mobile_public_products_product_name_key;
create unique index if not exists mobile_public_products_product_code_key
on public.mobile_public_products (product_code);

alter table public.mobile_public_products
    alter column product_code set not null,
    alter column product_name set not null;

create table if not exists public.mobile_public_machines (
    id uuid primary key default gen_random_uuid(),
    machine_id text not null unique
);

alter table public.mobile_public_machines add column if not exists machine_name text;
alter table public.mobile_public_machines add column if not exists running_product text;
alter table public.mobile_public_machines add column if not exists product_code text;
alter table public.mobile_public_machines add column if not exists product_name text;
alter table public.mobile_public_machines add column if not exists planned_qty numeric;
alter table public.mobile_public_machines add column if not exists completed_qty numeric;
alter table public.mobile_public_machines add column if not exists remaining_qty numeric;
alter table public.mobile_public_machines add column if not exists status text;
alter table public.mobile_public_machines add column if not exists mould_number text;
alter table public.mobile_public_machines add column if not exists material text;
alter table public.mobile_public_machines add column if not exists material_location text;
alter table public.mobile_public_machines add column if not exists colour_masterbatch text;
alter table public.mobile_public_machines add column if not exists operator_name text;
alter table public.mobile_public_machines add column if not exists pallet_qty numeric;
alter table public.mobile_public_machines add column if not exists notes text;
alter table public.mobile_public_machines add column if not exists display_order integer default 0;
alter table public.mobile_public_machines add column if not exists is_active boolean default true;
alter table public.mobile_public_machines add column if not exists updated_at timestamptz default now();

update public.mobile_public_machines
set is_active = coalesce(is_active, true),
    updated_at = coalesce(updated_at, now());

create table if not exists public.mobile_public_production_items (
    schedule_id text primary key,
    machine_id text not null,
    machine_name text,
    sequence integer default 0,
    status text not null,
    product_code text not null,
    product_name text,
    mould_number text,
    material text,
    material_location text,
    colour_masterbatch text,
    operator_name text,
    notes text,
    planned_qty numeric default 0,
    completed_qty numeric default 0,
    pallet_qty numeric,
    updated_at timestamptz default now(),
    is_active boolean default true
);

alter table public.mobile_public_production_items add column if not exists machine_name text;
alter table public.mobile_public_production_items add column if not exists sequence integer default 0;
alter table public.mobile_public_production_items add column if not exists product_name text;
alter table public.mobile_public_production_items add column if not exists mould_number text;
alter table public.mobile_public_production_items add column if not exists material text;
alter table public.mobile_public_production_items add column if not exists material_location text;
alter table public.mobile_public_production_items add column if not exists colour_masterbatch text;
alter table public.mobile_public_production_items add column if not exists operator_name text;
alter table public.mobile_public_production_items add column if not exists notes text;
alter table public.mobile_public_production_items add column if not exists planned_qty numeric default 0;
alter table public.mobile_public_production_items add column if not exists completed_qty numeric default 0;
alter table public.mobile_public_production_items add column if not exists pallet_qty numeric;
alter table public.mobile_public_production_items add column if not exists updated_at timestamptz default now();
alter table public.mobile_public_production_items add column if not exists is_active boolean default true;

create index if not exists mobile_production_machine_idx on public.mobile_public_production_items(machine_id);
create index if not exists mobile_production_status_idx on public.mobile_public_production_items(status);
create index if not exists mobile_production_sequence_idx on public.mobile_public_production_items(sequence);
create index if not exists mobile_production_active_idx on public.mobile_public_production_items(is_active);

create table if not exists public.mobile_public_moulds (
    mould_number text primary key,
    storage_location text,
    status text,
    issue_description text,
    associated_products text,
    updated_at timestamptz default now(),
    is_active boolean default true
);

create table if not exists public.mould_issue_records (
    issue_id uuid primary key default gen_random_uuid(),
    client_request_id text unique not null,
    mould_number text not null,
    related_product_code text,
    issue_type text not null,
    description text not null,
    status text not null default 'Open',
    operator_name text not null,
    source text not null default 'mobile',
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    resolved_at timestamptz,
    resolution_notes text
);

create table if not exists public.mould_issue_media (
    id uuid primary key default gen_random_uuid(),
    client_request_id text unique not null,
    issue_id uuid references public.mould_issue_records(issue_id),
    mould_number text not null,
    media_type text not null,
    storage_bucket text not null default 'mould-issue-media-temp',
    storage_path text not null,
    original_filename text not null,
    mime_type text,
    file_size bigint,
    sha256 text,
    archive_status text not null default 'WaitingForArchive',
    uploaded_by text,
    uploaded_at timestamptz default now(),
    archived_at timestamptz,
    cloud_deleted_at timestamptz,
    last_error text
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists stock_in_requests_set_updated_at on public.stock_in_requests;
create trigger stock_in_requests_set_updated_at
before update on public.stock_in_requests
for each row execute function public.set_updated_at();

drop trigger if exists mobile_public_products_set_updated_at on public.mobile_public_products;
create trigger mobile_public_products_set_updated_at
before update on public.mobile_public_products
for each row execute function public.set_updated_at();

drop trigger if exists mobile_public_machines_set_updated_at on public.mobile_public_machines;
create trigger mobile_public_machines_set_updated_at
before update on public.mobile_public_machines
for each row execute function public.set_updated_at();

alter table public.stock_in_requests enable row level security;
alter table public.mobile_public_products enable row level security;
alter table public.mobile_public_machines enable row level security;
alter table public.mobile_public_production_items enable row level security;
alter table public.mobile_public_moulds enable row level security;
alter table public.mould_issue_records enable row level security;
alter table public.mould_issue_media enable row level security;

drop policy if exists "mobile insert stock in requests" on public.stock_in_requests;
create policy "mobile insert stock in requests"
on public.stock_in_requests
for insert
to anon
with check (
    coalesce(source, 'mobile') = 'mobile'
    and status = 'pending'
    and client_request_id is not null
    and length(client_request_id) <= 120
    and product_name is not null
    and length(product_name) between 1 and 240
    and (product_code is null or length(product_code) <= 240)
    and operator_name is not null
    and length(operator_name) between 1 and 120
    and (note is null or length(note) <= 1000)
    and qty > 0
    and qty = floor(qty)
    and processed_at is null
    and error_message is null
    and coalesce(request_type, 'stock_in') in (
        'stock_in',
        'full_pallet',
        'custom',
        'waiting_for_wrap',
        'waiting_for_handle'
    )
    and (
        loose_status is null
        or loose_status in ('WaitingForWrap', 'WaitingForHandle')
    )
);

drop policy if exists "mobile read active products" on public.mobile_public_products;
create policy "mobile read active products"
on public.mobile_public_products
for select
to anon, authenticated
using (is_active = true);

drop policy if exists "mobile read active machines" on public.mobile_public_machines;
drop policy if exists "mobile read public machines" on public.mobile_public_machines;
create policy "mobile read active machines"
on public.mobile_public_machines
for select
to anon, authenticated
using (is_active = true);

drop policy if exists "anon read active production items" on public.mobile_public_production_items;
create policy "anon read active production items"
on public.mobile_public_production_items
for select
to anon, authenticated
using (is_active = true and status in ('Running', 'Next', 'Queued', 'Planned'));

drop policy if exists "anon read active moulds" on public.mobile_public_moulds;
create policy "anon read active moulds"
on public.mobile_public_moulds
for select
to anon, authenticated
using (is_active = true);

drop policy if exists "anon create mould issue" on public.mould_issue_records;
create policy "anon create mould issue"
on public.mould_issue_records
for insert
to anon
with check (
    source = 'mobile'
    and status = 'Open'
    and length(description) between 1 and 2000
);

drop policy if exists "anon create mould issue media" on public.mould_issue_media;
create policy "anon create mould issue media"
on public.mould_issue_media
for insert
to anon
with check (
    archive_status in ('PendingUpload', 'WaitingForArchive')
    and storage_bucket = 'mould-issue-media-temp'
);

insert into storage.buckets (id, name, public)
values ('mould-issue-media-temp', 'mould-issue-media-temp', false)
on conflict (id) do nothing;

drop policy if exists "anon upload temporary mould media" on storage.objects;
create policy "anon upload temporary mould media"
on storage.objects
for insert
to anon
with check (
    bucket_id = 'mould-issue-media-temp'
    and (storage.foldername(name))[1] is not null
);

revoke all on public.stock_in_requests from anon, authenticated;
revoke all on public.mobile_public_products from anon, authenticated;
revoke all on public.mobile_public_machines from anon, authenticated;
revoke all on public.mobile_public_production_items from anon, authenticated;
revoke all on public.mobile_public_moulds from anon, authenticated;
revoke all on public.mould_issue_records from anon, authenticated;
revoke all on public.mould_issue_media from anon, authenticated;

grant insert on public.stock_in_requests to anon;
grant select on public.mobile_public_products to anon, authenticated;
grant select on public.mobile_public_machines to anon, authenticated;
grant select on public.mobile_public_production_items to anon, authenticated;
grant select on public.mobile_public_moulds to anon, authenticated;
grant insert on public.mould_issue_records to anon;
grant insert on public.mould_issue_media to anon;

commit;
