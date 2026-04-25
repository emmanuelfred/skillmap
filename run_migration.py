"""
run_migration.py
Run this once from your skillmap_backend folder:
  python run_migration.py
"""
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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
    SELECT 1 FROM pg_policies
    WHERE tablename = 'skill_assessments'
    AND policyname = 'Talent reads own assessments'
  ) THEN
    CREATE POLICY "Talent reads own assessments"
      ON public.skill_assessments FOR SELECT
      USING (auth.uid() = user_id);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'skill_assessments'
    AND policyname = 'Talent inserts own assessments'
  ) THEN
    CREATE POLICY "Talent inserts own assessments"
      ON public.skill_assessments FOR INSERT
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;
"""

def run():
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"

    # Use the Postgres REST endpoint directly
    res = httpx.post(
        f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        json={"query": SQL},
        timeout=30,
    )

    if res.status_code in (200, 204):
        print("✅ Migration ran successfully!")
        return

    # exec_sql might not exist — use pg_meta instead
    print(f"exec_sql failed ({res.status_code}), trying pg_meta...")

    res2 = httpx.post(
        f"{SUPABASE_URL.replace('.supabase.co', '.supabase.co')}/pg-meta/v1/query",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        json={"query": SQL},
        timeout=30,
    )

    if res2.status_code in (200, 204):
        print("✅ Migration ran successfully via pg-meta!")
    else:
        print(f"❌ Failed: {res2.status_code}")
        print(res2.text[:500])
        print("\nTry the manual method below.")

if __name__ == "__main__":
    run()
