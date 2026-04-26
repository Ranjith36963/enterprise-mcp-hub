import type { MetadataRoute } from "next";
import type { JobListResponse } from "@/lib/types";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Static routes
  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: SITE_URL,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 1,
    },
    {
      url: `${SITE_URL}/dashboard`,
      lastModified: new Date(),
      changeFrequency: "hourly",
      priority: 0.9,
    },
    {
      url: `${SITE_URL}/profile`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 0.5,
    },
    {
      url: `${SITE_URL}/pipeline`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 0.6,
    },
  ];

  // Dynamic job pages — fetch up to 100 recent jobs.
  // INTENTIONAL: this is an unauthenticated server-side fetch (no user session
  // cookie exists in the build/edge context). The /api/jobs endpoint is kept
  // public read-only so the sitemap can index job IDs for Google for Jobs.
  // Job numeric IDs are not sensitive (no PII). If /api/jobs is ever gated
  // behind auth, add a SITEMAP_SERVICE_TOKEN env var here.
  let jobRoutes: MetadataRoute.Sitemap = [];
  try {
    const res = await fetch(
      `${API_BASE}/api/jobs?limit=100&min_score=30`,
      { next: { revalidate: 3600 } }
    );
    if (res.ok) {
      const data = (await res.json()) as JobListResponse;
      jobRoutes = data.jobs.map((job) => ({
        url: `${SITE_URL}/jobs/${job.id}`,
        lastModified: new Date(job.date_found),
        changeFrequency: "weekly" as const,
        priority: 0.7,
      }));
    }
  } catch {
    // Backend might be down at build time — proceed with static routes only
  }

  return [...staticRoutes, ...jobRoutes];
}
