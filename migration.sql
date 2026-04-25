-- Run this in Supabase SQL Editor
-- Adds extended fields to talents table and creates opportunities table

-- 1. Add extra_data JSONB column to talents (stores bio, portfolio, job_type, hourly_rate, languages)
ALTER TABLE public.talents
  ADD COLUMN IF NOT EXISTS extra_data JSONB DEFAULT '{}'::jsonb;

-- 2. Create opportunities table (used by FastAPI backend for matching)
CREATE TABLE IF NOT EXISTS public.opportunities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type TEXT NOT NULL CHECK (type IN ('Job', 'Gig', 'Apprenticeship', 'Training', 'Mentorship')),
  title TEXT NOT NULL,
  required_skills TEXT[] DEFAULT '{}',
  location TEXT,
  description TEXT,
  active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.opportunities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Opportunities viewable by everyone"
  ON public.opportunities FOR SELECT USING (true);

-- 3. Seed with sample opportunities
INSERT INTO public.opportunities (type, title, required_skills, location, description) VALUES
  ('Job', 'Junior Frontend Developer', ARRAY['React', 'HTML', 'CSS', 'JavaScript'], 'Remote', 'Build UIs for a Lagos-based fintech startup. 3-month contract with extension.'),
  ('Gig', 'Freelance Video Editor', ARRAY['Premiere Pro', 'Color Grading', 'Storytelling'], 'Remote', 'Edit short-form content for pan-African social media brands.'),
  ('Training', 'Data Analytics Bootcamp', ARRAY['Excel', 'SQL', 'Problem Solving'], 'Online', '8-week intensive — scholarship available for Global South applicants.'),
  ('Job', 'Social Media Manager', ARRAY['Instagram', 'TikTok', 'Content Strategy', 'Copywriting'], 'Remote', 'Manage social channels for a pan-African e-commerce brand.'),
  ('Mentorship', 'Tech Mentorship Program', ARRAY['Curiosity', 'Communication'], 'Online', '1:1 mentorship with senior engineers from top global tech companies.'),
  ('Apprenticeship', 'Mobile App Apprentice', ARRAY['Flutter', 'Dart', 'Mobile Development'], 'Accra, Ghana', '6-month paid apprenticeship at a Ghanaian startup.'),
  ('Job', 'UI/UX Designer', ARRAY['Figma', 'User Research', 'Prototyping', 'Design Systems'], 'Remote', 'Design intuitive products for African fintech and edtech startups.'),
  ('Gig', 'Graphic Designer', ARRAY['Illustrator', 'Photoshop', 'Branding'], 'Remote', 'Create brand identities and marketing materials for SMEs.'),
  ('Job', 'Backend Developer', ARRAY['Node.js', 'Python', 'PostgreSQL', 'REST APIs'], 'Remote', 'Build APIs and services for a fast-growing Nigerian startup.'),
  ('Training', 'Digital Marketing Certificate', ARRAY['Google Ads', 'SEO', 'Analytics', 'Content'], 'Online', 'Free certification from a leading global digital marketing platform.')
ON CONFLICT DO NOTHING;

-- Run this in your Supabase SQL Editor (after the existing migration.sql)
-- Creates skill_assessments table to persist AI assessment results per talent

CREATE TABLE IF NOT EXISTS public.skill_assessments (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  skill               TEXT NOT NULL,
  experience_level    TEXT NOT NULL,
  overall_score       INTEGER NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
  grade               TEXT NOT NULL CHECK (grade IN ('A', 'B', 'C', 'D', 'F')),
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

-- Fast lookup: latest assessment per user
CREATE INDEX IF NOT EXISTS skill_assessments_user_taken_idx
  ON public.skill_assessments (user_id, taken_at DESC);

-- Row-level security
ALTER TABLE public.skill_assessments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Talent reads own assessments"
  ON public.skill_assessments FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Talent inserts own assessments"
  ON public.skill_assessments FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Employers can view assessments of talent they're viewing
-- (optional — add later if you want employers to see badge on TalentDetail)
-- CREATE POLICY "Employers view talent assessments"
--   ON public.skill_assessments FOR SELECT
--   USING (EXISTS (SELECT 1 FROM public.employers WHERE user_id = auth.uid()));
