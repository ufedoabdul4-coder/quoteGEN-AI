-- quoteGEN · Supabase schema
--
-- Run this once in the Supabase dashboard → SQL Editor for the project that
-- quoteGEN will use. It creates the per-user tables, turns on Row Level
-- Security (the backend talks with the service-role key and bypasses RLS; the
-- policies below protect the tables if they are ever queried from the browser)
-- and creates the two private Storage buckets for generated artefacts.
--
-- Nothing else is needed: the FastAPI backend creates rows on demand.

-- ---------------------------------------------------------------------------
-- tables
-- ---------------------------------------------------------------------------

create table if not exists public.documents (
    user_id    uuid        not null references auth.users (id) on delete cascade,
    id         text        not null,
    record     jsonb       not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (user_id, id)
);

create table if not exists public.references (
    user_id    uuid        not null references auth.users (id) on delete cascade,
    id         text        not null,
    kind       text        not null default 'reference',
    meta       jsonb       not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (user_id, id)
);

create table if not exists public.settings (
    user_id            uuid primary key references auth.users (id) on delete cascade,
    active_template_id text
);

create table if not exists public.profiles (
    user_id       uuid primary key references auth.users (id) on delete cascade,
    business_type text not null default '',
    data          jsonb not null
);

create table if not exists public.billing_accounts (
    user_id uuid primary key references auth.users (id) on delete cascade,
    free_quotations_used integer not null default 0 check (free_quotations_used >= 0),
    paid_until timestamptz,
    updated_at timestamptz not null default now()
);

create table if not exists public.quotation_usage (
    user_id uuid not null references auth.users (id) on delete cascade,
    document_id text not null,
    created_at timestamptz not null default now(),
    primary key (user_id, document_id)
);

create table if not exists public.billing_payments (
    tx_ref text primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    amount_ngn integer not null check (amount_ngn > 0),
    currency text not null default 'NGN' check (currency = 'NGN'),
    status text not null default 'pending' check (status in ('pending', 'successful', 'failed')),
    transaction_id text unique,
    created_at timestamptz not null default now()
);

alter table public.profiles
    add column if not exists business_type text not null default '';

update public.profiles
set business_type = data->>'business_type'
where business_type = ''
  and coalesce(data->>'business_type', '') <> '';

create index if not exists documents_user_updated_idx on public.documents (user_id, updated_at desc);
create index if not exists references_user_kind_idx  on public.references (user_id, kind);
create index if not exists profiles_business_type_idx on public.profiles (business_type);

-- ---------------------------------------------------------------------------
-- row level security
-- ---------------------------------------------------------------------------

alter table public.documents  enable row level security;
alter table public.references enable row level security;
alter table public.settings   enable row level security;
alter table public.profiles   enable row level security;
alter table public.billing_accounts enable row level security;
alter table public.quotation_usage enable row level security;
alter table public.billing_payments enable row level security;

drop policy if exists documents_owner on public.documents;
create policy documents_owner on public.documents
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists references_owner on public.references;
create policy references_owner on public.references
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists settings_owner on public.settings;
create policy settings_owner on public.settings
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists profiles_owner on public.profiles;
create policy profiles_owner on public.profiles
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists billing_accounts_owner on public.billing_accounts;
create policy billing_accounts_owner on public.billing_accounts
    for select using (auth.uid() = user_id);

drop policy if exists quotation_usage_owner on public.quotation_usage;
create policy quotation_usage_owner on public.quotation_usage
    for select using (auth.uid() = user_id);

drop policy if exists billing_payments_owner on public.billing_payments;
create policy billing_payments_owner on public.billing_payments
    for select using (auth.uid() = user_id);

create index if not exists billing_payments_user_created_idx
    on public.billing_payments (user_id, created_at desc);
create index if not exists billing_accounts_paid_until_idx
    on public.billing_accounts (paid_until);

create or replace function public.consume_quotation(p_user_id uuid, p_document_id text)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    account public.billing_accounts%rowtype;
begin
    insert into public.billing_accounts (user_id)
    values (p_user_id)
    on conflict (user_id) do nothing;

    select * into account
    from public.billing_accounts
    where user_id = p_user_id
    for update;

    if exists (
        select 1 from public.quotation_usage
        where user_id = p_user_id and document_id = p_document_id
    ) then
        return true;
    end if;

    if account.paid_until is null or account.paid_until <= now() then
        if account.free_quotations_used >= 10 then
            return false;
        end if;
        update public.billing_accounts
        set free_quotations_used = free_quotations_used + 1,
            updated_at = now()
        where user_id = p_user_id;
    end if;

    insert into public.quotation_usage (user_id, document_id)
    values (p_user_id, p_document_id);
    return true;
end;
$$;

create or replace function public.activate_monthly_plan(p_tx_ref text, p_transaction_id text)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    payment public.billing_payments%rowtype;
begin
    select * into payment
    from public.billing_payments
    where tx_ref = p_tx_ref
    for update;

    if not found then
        return false;
    end if;
    if payment.status = 'successful' then
        return payment.transaction_id = p_transaction_id;
    end if;
    if payment.status <> 'pending' then
        return false;
    end if;

    update public.billing_payments
    set status = 'successful',
        transaction_id = p_transaction_id
    where tx_ref = p_tx_ref;

    insert into public.billing_accounts (user_id, paid_until)
    values (payment.user_id, now() + interval '1 month')
    on conflict (user_id) do update
    set paid_until = greatest(
            coalesce(public.billing_accounts.paid_until, now()),
            now()
        ) + interval '1 month',
        updated_at = now();

    return true;
end;
$$;

revoke all on function public.consume_quotation(uuid, text) from public, anon, authenticated;
grant execute on function public.consume_quotation(uuid, text) to service_role;
revoke all on function public.activate_monthly_plan(text, text) from public, anon, authenticated;
grant execute on function public.activate_monthly_plan(text, text) to service_role;

-- ---------------------------------------------------------------------------
-- storage buckets (private)
-- ---------------------------------------------------------------------------

insert into storage.buckets (id, name, public)
values ('previews', 'previews', false)
on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
values ('references', 'references', false)
on conflict (id) do nothing;

-- Each object lives under "<user_id>/…"; let a signed-in user read only their
-- own folder. Writes are performed by the backend with the service-role key.
drop policy if exists previews_owner_read on storage.objects;
create policy previews_owner_read on storage.objects
    for select using (
        bucket_id = 'previews'
        and auth.uid()::text = (storage.foldername(name))[1]
    );

drop policy if exists references_owner_read on storage.objects;
create policy references_owner_read on storage.objects
    for select using (
        bucket_id = 'references'
        and auth.uid()::text = (storage.foldername(name))[1]
    );
