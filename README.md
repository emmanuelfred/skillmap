# SkillMap — AI-Powered Talent Platform for the Global South

> Making invisible talent visible. AI skill extraction, opportunity matching, and employer discovery — built for Nigeria, Ghana, Uganda, and beyond.

---

## 🗂️ Project Structure

```
SkillMap/
├── team-skill-up-hackathon/     ← Frontend (React + Vite + Tailwind)
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── contexts/
│   │   └── integrations/supabase/
│   └── .env
│
└── skillmap_backend/            ← Backend (FastAPI + Groq AI)
    ├── app/
    │   ├── api/
    │   ├── core/
    │   ├── models/
    │   └── services/
    ├── main.py
    ├── requirements.txt
    └── .env
```

---

## ⚡ Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Git

---

## 1️⃣ Clone the Repository

```bash
git clone https://github.com/YOUR_ORG/team-skill-up-hackathon.git
cd team-skill-up-hackathon
```

---

## 2️⃣ Frontend Setup

```bash
# From the repo root
npm install
```

Create a `.env` file in the root:

```env
VITE_API_URL="http://127.0.0.1:8000/api"
VITE_SUPABASE_URL="https://kdpbypejngxvcxeobfuj.supabase.co"
VITE_SUPABASE_PUBLISHABLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

> 📌 Get the Supabase keys from the team lead or Supabase dashboard → API Keys.

Start the frontend:

```bash
npm run dev
# Runs on http://localhost:8080
```

---

## 3️⃣ Backend Setup

```bash
# Navigate to backend folder
cd skillmap_backend

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file inside `skillmap_backend/`:

```env
# Groq AI
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx

# Supabase (backend uses SECRET key — never expose in frontend)
SUPABASE_URL=https://kdpbypejngxvcxeobfuj.supabase.co
SUPABASE_KEY=sb_secret_xxxxxxxxxxxxxxxxxxxxxxxx

# Gmail SMTP (for auth emails)
GMAIL_USER=yourteam@gmail.com
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxxxxxx

# App
FRONTEND_URL=http://localhost:8080
```

> 📌 Get API keys from team lead. Gmail App Password: myaccount.google.com → Security → App Passwords.

Start the backend:

```bash
# Inside skillmap_backend/ with venv active
uvicorn main:app --reload
# Runs on http://localhost:8000
# Swagger UI: http://localhost:8000/docs
```

---

## 4️⃣ Database Migrations

After starting both servers, go to:

```
http://localhost:8080/setup/migrations
```

Click **"Check all"** then **"Run all migrations"** to seed the database with opportunities and verify all tables exist.

For tables that need SQL (skill_assessments, job_applications), run the SQL files in **Supabase → SQL Editor**:
- `skillmap_backend/migration.sql`
- `skillmap_backend/job_applications_migration.sql`

---

## 🔑 Getting API Keys

### Groq API Key (AI)
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up → Create API Key
3. Free tier is enough for development

### Supabase Keys
Ask the team lead for:
- `SUPABASE_URL` — project URL
- `VITE_SUPABASE_PUBLISHABLE_KEY` — for frontend (anon/publishable key)
- `SUPABASE_KEY` — for backend only (secret key — never share publicly)

### Gmail App Password
1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Security → Enable 2-Step Verification
3. Search "App Passwords" → Create one for "Mail"
4. Copy the 16-character password (no spaces)

---

## 🚀 All API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/health` | Health check |
| `POST` | `/api/v1/process-talent` | Extract skills + match opportunities |
| `GET`  | `/api/v1/opportunities` | List all opportunities |
| `POST` | `/api/v1/talent/parse-cv` | Parse CV file → auto-fill profile |
| `POST` | `/api/v1/talent/screen` | AI profile screening + score |
| `POST` | `/api/v1/talent/external-jobs` | Live job matches from external boards |
| `POST` | `/api/v1/assessment/generate` | Generate skill assessment questions |
| `POST` | `/api/v1/assessment/evaluate` | Score assessment answers |
| `POST` | `/api/v1/founder/analyze` | Founder AI Setup Assistant |

Full docs at `http://localhost:8000/docs`

---

## 🌐 App Pages

| Route | Description | Access |
|-------|-------------|--------|
| `/` | Landing page | Public |
| `/auth` | Login / Signup | Public |
| `/opportunities` | Browse & apply to jobs | Public |
| `/map` | Live talent map | Public |
| `/talent/dashboard` | Talent home | Talent only |
| `/talent/edit` | Edit profile + CV upload | Talent only |
| `/talent/assessment` | AI skill assessment | Talent only |
| `/employer/dashboard` | Employer home | Employer only |
| `/employer/founder-assistant` | AI startup setup wizard | Employer only |
| `/employer/jobs/new` | Post a job | Employer only |
| `/employer/jobs/:id/applications` | View & manage applicants | Employer only |
| `/employer/talent` | Search talent directory | Employer only |
| `/setup/migrations` | Run DB migrations | Logged in |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, Python 3.11, Pydantic |
| Database | Supabase (PostgreSQL) |
| Auth | Supabase Auth |
| AI | Groq (LLaMA 3.3 70B) |
| Email | Gmail SMTP |
| External Jobs | Arbeitnow, Himalayas, FindWork APIs |
| Deployment | Render (backend), Lovable/Vercel (frontend) |

---

## 🧑‍💻 Development Workflow

```bash
# Terminal 1 — Frontend
cd team-skill-up-hackathon
npm run dev

# Terminal 2 — Backend
cd skillmap_backend
source venv/bin/activate   # or venv\Scripts\activate on Windows
uvicorn main:app --reload
```

Both must be running at the same time for full functionality.

---

## 🐛 Common Issues

**Backend won't start — `pydantic_settings` missing:**
```bash
pip install pydantic-settings
```

**Backend 404 on `/api/v1/talent/parse-cv`:**
```bash
pip install python-multipart
```

**PDF parsing fails:**
```bash
pip install pdfplumber
```

**Frontend can't connect to backend:**
- Make sure backend is running on port 8000
- Check `VITE_API_URL` in frontend `.env` — should be `http://127.0.0.1:8000/api`
- No trailing slash

**Supabase "invalid API key":**
- Frontend uses the **publishable** key (`sb_publishable_...` or `eyJ...`)
- Backend uses the **secret** key (`sb_secret_...`)
- Never swap them

---

## 👥 Team

| Role | Responsibility |
|------|---------------|
| Frontend | React pages, Supabase queries, UI components |
| Backend | FastAPI endpoints, Groq AI integration, email |
| Design | Tailwind styling, component design |
| DevOps | Render deployment, env management |

---

## 📦 Deployment (Render)

1. Push backend to GitHub
2. Render → New Web Service → Connect repo
3. **Root Directory:** `skillmap_backend`
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add all `.env` variables in Render → Environment tab
7. Deploy

---

*Built for the Global South. Making invisible talent visible.*