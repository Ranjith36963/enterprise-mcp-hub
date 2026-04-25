// ---------------------------------------------------------------------------
// Job360 Frontend — TypeScript types matching FastAPI Pydantic schemas
// ---------------------------------------------------------------------------

// ---- Job ----

export interface JobResponse {
  id: number;
  title: string;
  company: string;
  location: string;
  salary: string | null;
  match_score: number;
  source: string;
  date_found: string;
  apply_url: string;
  visa_flag: boolean;
  job_type: string;
  experience_level: string;
  // 8D score breakdown
  role: number;
  skill: number;
  seniority_score: number;
  experience: number;
  credentials: number;
  location_score: number;
  recency: number;
  semantic: number;
  penalty: number;
  // Skill analysis
  matched_skills: string[];
  missing_required: string[];
  transferable_skills: string[];
  // User action
  action: string | null;
  bucket: string;
  // Step-1 B6 — date-model fields (Pillar 3 Batch 1).
  posted_at?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  date_confidence?: string | null;
  staleness_state?: string | null;
  // Step-1 B6 — enrichment fields (Pillar 2 Batch 2.5 subset).
  title_canonical?: string | null;
  seniority?: string | null;
  employment_type?: string | null;
  workplace_type?: string | null;
  visa_sponsorship?: boolean | null;
  salary_min_gbp?: number | null;
  salary_max_gbp?: number | null;
  salary_period?: string | null;
  salary_currency_original?: string | null;
  required_skills?: string[] | null;
  nice_to_have_skills?: string[] | null;
  industry?: string | null;
  years_experience_min?: number | null;
}

export interface JobListResponse {
  jobs: JobResponse[];
  total: number;
  filters_applied: Record<string, unknown>;
}

export interface JobFilters {
  hours?: number;
  min_score?: number;
  source?: string;
  bucket?: string;
  action?: string;
  visa_only?: boolean;
  limit?: number;
  offset?: number;
  mode?: string;
}

// ---- Profile ----

export interface ProfileSummary {
  is_complete: boolean;
  job_titles: string[];
  skills_count: number;
  cv_length: number;
  has_linkedin: boolean;
  has_github: boolean;
  education: string[];
  experience_level: string;
}

export interface CVDetail {
  raw_text: string;
  skills: string[];
  job_titles: string[];
  education: string[];
  certifications: string[];
  summary_text: string;
  experience_text: string;
}

export interface ProfileResponse {
  summary: ProfileSummary;
  preferences: Record<string, unknown>;
  cv_detail?: CVDetail | null;
}

export interface PreferencesRequest {
  target_job_titles?: string[];
  additional_skills?: string[];
  excluded_skills?: string[];
  preferred_locations?: string[];
  industries?: string[];
  salary_min?: number | null;
  salary_max?: number | null;
  work_arrangement?: string;
  experience_level?: string;
  negative_keywords?: string[];
  about_me?: string;
  excluded_companies?: string[];
}

// ---- Search ----

export interface SearchStartResponse {
  run_id: string;
  status: string;
}

export interface SearchStatusResponse {
  run_id: string;
  status: string;
  progress: string;
  result: Record<string, unknown> | null;
}

// ---- Actions ----

export interface ActionRequest {
  action: "liked" | "applied" | "not_interested";
  notes?: string;
}

export interface ActionResponse {
  ok: boolean;
  job_id: number;
  action: string;
}

// ---- Pipeline ----

export interface PipelineAdvanceRequest {
  stage: string;
}

export interface PipelineApplication {
  job_id: number;
  stage: string;
  created_at: string;
  updated_at: string;
  notes: string;
  title?: string;
  company?: string;
}

// ---- Status / Health / Sources ----

export interface StatusResponse {
  jobs_total: number;
  last_run: Record<string, unknown> | null;
  sources_active: number;
  sources_total: number;
  profile_exists: boolean;
}

export interface SourceInfo {
  name: string;
  type: string;
  health: Record<string, unknown>;
}

export interface HealthResponse {
  status: string;
  version: string;
}
