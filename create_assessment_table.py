"""
create_assessment_table.py
Creates the skill_assessments table by using Supabase's REST API
with the secret key — same way the app already talks to Supabase.

Run with:
  python create_assessment_table.py
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def check_table_exists() -> bool:
    """Check if skill_assessments already exists by querying it."""
    res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/skill_assessments?limit=1",
        headers=HEADERS,
        timeout=15,
    )
    return res.status_code == 200


def create_table():
    """
    Use Supabase's pg-meta API to run raw SQL.
    This works with the service_role (secret) key.
    """
    PROJECT_REF = SUPABASE_URL.replace("https://", "").split(".")[0]

    SQL = """
CREATE TABLE IF NOT EXISTS public.skill_assessments (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  skill               TEXT NOT NULL,
  experience_level    TEXT NOT NULL,
  overall_score       INTEGER NOT NULL,
  grade               TEXT NOT NULL,
  badge               TEXT NOT NULL,
  correct_answers     INTEGER NOT NULL,
  total_questions     INTEGER NOT NULL,
  time_taken_seconds  INTEGER,
  strengths           TEXT[]  DEFAULT '{}',
  weak_areas          TEXT[]  DEFAULT '{}',
  recommendation      TEXT,
  skill_breakdown     JSONB   DEFAULT '[]',
  taken_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS skill_assessments_user_taken_idx
  ON public.skill_assessments (user_id, taken_at DESC);

ALTER TABLE public.skill_assessments ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'skill_assessments'
    AND policyname = 'Talent reads own assessments'
  ) THEN
    CREATE POLICY "Talent reads own assessments"
      ON public.skill_assessments FOR SELECT
      USING (auth.uid() = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'skill_assessments'
    AND policyname = 'Talent inserts own assessments'
  ) THEN
    CREATE POLICY "Talent inserts own assessments"
      ON public.skill_assessments FOR INSERT
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;
"""

    # Try Supabase pg-meta endpoint (available on all plans)
    res = httpx.post(
        f"https://{PROJECT_REF}.supabase.co/pg-meta/v1/query",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        json={"query": SQL},
        timeout=30,
    )

    if res.status_code in (200, 201, 204):
        return True, "pg-meta"

    # Try management API
    res2 = httpx.post(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        headers={
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        json={"query": SQL},
        timeout=30,
    )

    if res2.status_code in (200, 201, 204):
        return True, "management API"

    return False, f"pg-meta: {res.status_code} | mgmt: {res2.status_code}\n{res.text[:200]}"


def main():
    print(f"Project: {SUPABASE_URL}")
    print()

    # Check if already exists
    print("Checking if table already exists...")
    if check_table_exists():
        print("✅ skill_assessments table already exists! Nothing to do.")
        print("   Take the assessment — badge will show on dashboard.")
        return

    print("Table not found. Creating...")
    success, info = create_table()

    if success:
        print(f"✅ Table created successfully via {info}!")
        print("   Take the assessment — badge will show on dashboard.")
    else:
        print(f"❌ Could not create table automatically: {info}")
        print()
        print("=" * 60)
        print("MANUAL OPTION:")
        print("Ask your friend to paste this in Supabase SQL Editor:")
        print("=" * 60)
        print("""
CREATE TABLE IF NOT EXISTS public.skill_assessments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  skill TEXT NOT NULL,
  experience_level TEXT NOT NULL,
  overall_score INTEGER NOT NULL,
  grade TEXT NOT NULL,
  badge TEXT NOT NULL,
  correct_answers INTEGER NOT NULL,
  total_questions INTEGER NOT NULL,
  time_taken_seconds INTEGER,
  strengths TEXT[] DEFAULT '{}',
  weak_areas TEXT[] DEFAULT '{}',
  recommendation TEXT,
  skill_breakdown JSONB DEFAULT '[]',
  taken_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.skill_assessments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Talent reads own assessments" ON public.skill_assessments FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Talent inserts own assessments" ON public.skill_assessments FOR INSERT WITH CHECK (auth.uid() = user_id);
""")


if __name__ == "__main__":
    main()
