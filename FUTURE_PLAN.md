# Job360 Startup Roadmap — From Prototype to Product

## Context

Job360 has a working Python engine: 50 job sources, 8D scoring, embeddings, cross-encoder reranking, LLM enrichment, dedup, and a Streamlit prototype dashboard. The engine is proven but limited by free data sources (3.9% yield, 19 fresh jobs/day vs 2,000+ on LinkedIn). The frontend (Streamlit) is a prototype — not production-grade for sharing with users.

This plan charts the path from current prototype to a deployable, shareable startup product.

---

## Phase 1: FastAPI Backend (Week 1-2)

**Goal:** Wrap the existing Python engine as a REST API so any frontend can consume it.

### What to Build

Create `src/api/` with FastAPI endpoints that expose the existing engine:

```
src/api/
├── main.py          # FastAPI app, CORS, lifespan
├── routes/
│   ├── search.py    # POST /api/search → triggers run_search()
│   ├── jobs.py      # GET /api/jobs → returns scored, bucketed results
│   ├── profile.py   # POST /api/profile → upload CV, save preferences
│   ├── actions.py   # POST /api/actions → like/apply/not-interested
│   └── status.py    # GET /api/status → last run stats, source health
└── schemas.py       # Pydantic request/response models
```

### Key Design Decisions

- **Reuse everything** — `run_search()`, `JobScorer`, `JobDatabase`, `load_profile()`, `generate_search_config()` all stay as-is. FastAPI just wraps them.
- **Background tasks** — Search runs take 2-4 minutes. Use FastAPI BackgroundTasks or Celery to run searches async. Return a job ID, frontend polls for completion.
- **SQLite stays** — For MVP, SQLite is fine. Supabase/Postgres later if needed.
- **Auth** — Start with simple API key or JWT. Multi-user comes in Phase 4.

### Endpoints

| Method | Path | What It Does |
|--------|------|-------------|
| `POST /api/profile` | Upload CV (PDF/DOCX), save preferences | Returns parsed profile summary |
| `POST /api/profile/linkedin` | Upload LinkedIn ZIP | Merges into profile |
| `POST /api/profile/github` | GitHub username | Fetches and merges |
| `GET /api/profile` | Get current profile | Returns profile JSON |
| `POST /api/search` | Trigger pipeline run | Returns run_id (async) |
| `GET /api/search/{run_id}` | Poll search status | Returns progress or results |
| `GET /api/jobs` | Get jobs with filters | Query params: hours, min_score, source, bucket |
| `GET /api/jobs/{id}` | Single job detail | Full match_data, skills breakdown |
| `POST /api/jobs/{id}/action` | Like/Apply/Not Interested | Updates user_actions |
| `GET /api/status` | Pipeline health | Last run stats, source health |
| `GET /api/sources` | List all sources | Name, type, status |

### Verification

```bash
uvicorn src.api.main:app --reload --port 8000
curl http://localhost:8000/api/status
curl -X POST http://localhost:8000/api/profile -F "cv=@path/to/cv.pdf"
curl -X POST http://localhost:8000/api/search
```

---

## Phase 2: Next.js Frontend (Week 3-5)

**Goal:** Build a polished, mobile-responsive web app that creates the "wow moment."

### Tech Stack

```
Next.js 15 (App Router) + TypeScript + Tailwind CSS + shadcn/ui
```

### Pages

| Page | Route | What It Shows |
|------|-------|-------------|
| **Landing** | `/` | Hero, value prop, "Upload CV to Start" CTA |
| **Dashboard** | `/dashboard` | Job cards in time buckets (24h, 48h, 3d, 5d, 7d), filters, search |
| **Job Detail** | `/jobs/[id]` | Full description, 8D score radar chart, skill match/gap, apply button |
| **Profile** | `/profile` | CV upload, preferences form, LinkedIn/GitHub connect |
| **Pipeline** | `/pipeline` | Application tracking kanban (applied → interview → offer) |

### Key UI Components

```
components/
├── JobCard.tsx          # Score badge, title, company, salary, time bucket tag
├── ScoreRadar.tsx       # 8D radar chart (Recharts)
├── SkillMatch.tsx       # Matched (green) / Missing (red) / Transferable (yellow)
├── TimeBuckets.tsx      # Horizontal tabs: 24h | 48h | 3d | 5d | 7d
├── FilterPanel.tsx      # Score range, location, source, visa, salary
├── ProfileSetup.tsx     # CV drag-drop, preferences form
├── SearchButton.tsx     # Triggers search, shows progress bar
└── Layout.tsx           # Navbar, sidebar, responsive shell
```

### Design Principles

- **Mobile-first** — Job seekers search on phones
- **Score is king** — Big score badge on every card, color-coded (green >70, yellow >50, red <30)
- **Time buckets are tabs, not sections** — Click "Last 24h" tab, see only today's jobs
- **One-click apply** — Every job card has a direct "Apply" link that opens employer's page
- **Dark mode** — Default dark, toggle light

---

## Phase 3: Deploy (Week 5-6)

**Goal:** Live on the internet with a custom domain.

### Architecture

```
job360.app (or job360.co.uk)
         │
         ├── Frontend: Vercel (free tier)
         │   └── Next.js app
         │       └── calls API at api.job360.app
         │
         └── Backend: Railway ($5/month)
             └── FastAPI + Python engine
                 ├── SQLite (local file on Railway volume)
                 ├── sentence-transformers models (cached)
                 └── .env (SerpAPI key, LLM keys)
```

### Deployment Steps

1. **Backend → Railway**
   - Dockerfile with Python 3.11, requirements.txt, uvicorn
   - Volume mount for `data/` (SQLite, exports, logs)
   - Env vars: `SERPAPI_KEY`, LLM provider keys
   - Custom domain: `api.job360.app`

2. **Frontend → Vercel**
   - `vercel deploy` from frontend directory
   - Set `NEXT_PUBLIC_API_URL=https://api.job360.app`
   - Custom domain: `job360.app`

3. **Domain** — Buy `job360.app` or `job360.co.uk` (~£10/year)

### Monthly Costs

| Service | Cost | What |
|---------|------|------|
| Railway | $5/mo | Backend hosting |
| Vercel | $0 | Frontend (free tier) |
| Domain | ~£1/mo | Custom domain |
| SerpAPI | $75/mo | Job data (when ready) |
| LLM providers | $0 | Free tier (Groq, Cerebras, Gemini) |
| **Total** | **~$81/mo** | Full production stack |

---

## Phase 4: Multi-User & Auth (Week 7-8)

**Goal:** Multiple job seekers can use Job360 with their own profiles.

### Changes

- **Auth:** Supabase Auth (free tier, Google/GitHub OAuth)
- **Database:** Migrate from SQLite to Supabase Postgres (free tier, 500MB)
  - Each user gets their own profile, search results, actions
  - Schema: add `user_id` column to jobs, user_actions, applications
- **Profile isolation:** Each user uploads their own CV, sees their own results
- **Search isolation:** Each user's pipeline run uses their own SearchConfig

### User Flow

```
1. User signs up (Google OAuth via Supabase)
2. Uploads CV → profile saved to their user record
3. Sets preferences → saved
4. Clicks "Search" → pipeline runs with THEIR profile
5. Sees THEIR scored results in THEIR dashboard
6. Likes/applies → tracked per user
```

---

## Phase 5: Growth & Monetization (Month 2+)

### Free Tier
- 1 search per day
- Top 20 results only
- Basic score (no detailed breakdown)

### Pro Tier (£10/month)
- Unlimited searches
- Full 8D score breakdown with skill gap analysis
- Email/Slack/Discord alerts for new high-scoring jobs
- Application tracking pipeline
- CSV/report exports

### Revenue Math

```
$75/mo SerpAPI + $5/mo Railway = $80/mo costs
8 Pro users × £10/mo = £80/mo → break even
20 Pro users × £10/mo = £200/mo → profitable
```

---

## Immediate Action: Install python-jobspy

**Do this today — zero cost, zero risk, immediate impact.**

```bash
pip install python-jobspy
```

The `JobSpySource` code already exists. This unlocks Indeed + Glassdoor immediately. Combined with the existing 43 free sources, this provides a viable MVP dataset while building towards SerpAPI.

---

## Summary Timeline

| Week | Milestone | Deliverable |
|------|-----------|------------|
| **Now** | Install python-jobspy | Indeed + Glassdoor data flowing |
| **1-2** | FastAPI backend | REST API wrapping engine |
| **3-5** | Next.js frontend | Polished web app with "wow moment" |
| **5-6** | Deploy | Live at job360.app |
| **7-8** | Multi-user | Auth + per-user profiles |
| **Month 2** | Launch | Share with friends, LinkedIn, collect feedback |
| **Month 3** | Monetize | Pro tier, break even at 8 users |
