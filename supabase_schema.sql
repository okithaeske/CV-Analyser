-- Supabase schema for Skill Gap Suggestions app
-- Run in Supabase SQL editor

okitha123456789010

create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  created_at timestamptz not null default now()
);

create table if not exists resumes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  file_path text,
  raw_text text,
  created_at timestamptz not null default now()
);

create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  company text,
  raw_text text not null,
  created_at timestamptz not null default now()
);

create table if not exists analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  resume_id uuid references resumes(id) on delete set null,
  job_id uuid references jobs(id) on delete set null,
  target_role text check (target_role in ('backend','fullstack','cloud_devops')) not null,
  result_json jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists skills (
  id text primary key,
  canonical_name text not null,
  aliases text[] not null default '{}',
  category text not null,
  roles text[] not null default '{}',
  level text not null default 'supplementary'
);

create table if not exists learning_resources (
  id uuid primary key default gen_random_uuid(),
  skill_id text not null references skills(id) on delete cascade,
  title text not null,
  provider text,
  url text,
  difficulty text,
  duration_hours numeric,
  created_at timestamptz not null default now()
);

-- Useful indexes
create index if not exists idx_resumes_user_id on resumes(user_id);
create index if not exists idx_jobs_user_id on jobs(user_id);
create index if not exists idx_analyses_user_id on analyses(user_id);
create index if not exists idx_skills_category on skills(category);

-- Row Level Security (RLS)
alter table profiles enable row level security;
alter table resumes enable row level security;
alter table jobs enable row level security;
alter table analyses enable row level security;
alter table learning_resources enable row level security;

-- Policies: users can access only their own rows
create policy if not exists "profiles_select_own" on profiles
for select using (auth.uid() = id);

create policy if not exists "profiles_upsert_own" on profiles
for insert with check (auth.uid() = id);

create policy if not exists "profiles_update_own" on profiles
for update using (auth.uid() = id);

create policy if not exists "resumes_select_own" on resumes
for select using (auth.uid() = user_id);

create policy if not exists "resumes_insert_own" on resumes
for insert with check (auth.uid() = user_id);

create policy if not exists "resumes_update_own" on resumes
for update using (auth.uid() = user_id);

create policy if not exists "jobs_select_own" on jobs
for select using (auth.uid() = user_id);

create policy if not exists "jobs_insert_own" on jobs
for insert with check (auth.uid() = user_id);

create policy if not exists "jobs_update_own" on jobs
for update using (auth.uid() = user_id);

create policy if not exists "analyses_select_own" on analyses
for select using (auth.uid() = user_id);

create policy if not exists "analyses_insert_own" on analyses
for insert with check (auth.uid() = user_id);

create policy if not exists "learning_resources_read_all" on learning_resources
for select using (true);

-- skills table is shared reference data (no RLS needed, but you can enable if you prefer)
