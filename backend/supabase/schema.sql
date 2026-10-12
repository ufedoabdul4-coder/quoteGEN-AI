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
    user_id uuid primary key references auth.users (id) on delete cascade,
    data    jsonb not null
);

create index if not exists documents_user_updated_idx on public.documents (user_id, updated_at desc);
create index if not exists references_user_kind_idx  on public.references (user_id, kind);

-- ---------------------------------------------------------------------------
-- row level security
-- ---------------------------------------------------------------------------

alter table public.documents  enable row level security;
alter table public.references enable row level security;
alter table public.settings   enable row level security;
alter table public.profiles   enable row level security;

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
