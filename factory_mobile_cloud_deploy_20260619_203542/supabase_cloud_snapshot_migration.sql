alter table public.mobile_public_machines add column if not exists product_code text;
alter table public.stock_in_requests alter column product_code type text;
alter table public.mobile_public_products alter column product_code type text;

alter table public.mobile_public_machines add column if not exists product_name text;
alter table public.mobile_public_machines add column if not exists mould_number text;
alter table public.mobile_public_machines add column if not exists material text;
alter table public.mobile_public_machines add column if not exists colour_masterbatch text;

alter table public.stock_in_requests add column if not exists client_request_id text;

update public.stock_in_requests
set client_request_id = coalesce(nullif(client_request_id, ''), id::text)
where client_request_id is null or client_request_id = '';

create unique index if not exists stock_in_requests_client_request_id_key
on public.stock_in_requests (client_request_id);

alter table public.stock_in_requests
alter column client_request_id set not null;

alter table public.stock_in_requests enable row level security;
alter table public.mobile_public_products enable row level security;
alter table public.mobile_public_machines enable row level security;

drop policy if exists "mobile insert stock in requests" on public.stock_in_requests;
create policy "mobile insert stock in requests"
on public.stock_in_requests
for insert
to anon
with check (
    coalesce(source, 'mobile') = 'mobile'
    and status = 'pending'
    and client_request_id is not null
    and (product_code is null or length(product_code) <= 240)
    and qty > 0
    and qty = floor(qty)
    and processed_at is null
    and error_message is null
);

drop policy if exists "mobile read active products" on public.mobile_public_products;
create policy "mobile read active products"
on public.mobile_public_products
for select
to anon
using (is_active = true);

drop policy if exists "mobile read active machines" on public.mobile_public_machines;
drop policy if exists "mobile read public machines" on public.mobile_public_machines;
create policy "mobile read active machines"
on public.mobile_public_machines
for select
to anon
using (is_active = true);

revoke all on public.stock_in_requests from anon, authenticated;
revoke all on public.mobile_public_products from anon, authenticated;
revoke all on public.mobile_public_machines from anon, authenticated;

grant insert on public.stock_in_requests to anon;
grant select on public.mobile_public_products to anon;
grant select on public.mobile_public_machines to anon;

