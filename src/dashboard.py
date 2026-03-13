"""Job360 Web Dashboard — Streamlit UI for browsing, filtering, and managing job results."""

import os
import sqlite3
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path so "src" package resolves
# when Streamlit runs this file directly.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st
import pandas as pd
import plotly.express as px

from src.config.settings import DB_PATH, EXPORTS_DIR, MIN_MATCH_SCORE

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Job360 Dashboard",
    page_icon="\U0001F4BC",
    layout="wide",
    initial_sidebar_state="expanded",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Database helpers (synchronous – Streamlit-friendly)
# ---------------------------------------------------------------------------
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=60)
def load_jobs() -> pd.DataFrame:
    conn = _get_conn()
    try:
        df = pd.read_sql_query("SELECT * FROM jobs ORDER BY match_score DESC", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

    if df.empty:
        return df

    df["visa_flag"] = df["visa_flag"].astype(bool)
    df["first_seen"] = pd.to_datetime(df["first_seen"], errors="coerce")
    df["date_found"] = pd.to_datetime(df["date_found"], errors="coerce")

    # Formatted salary column
    def _fmt_salary(row):
        smin, smax = row.get("salary_min"), row.get("salary_max")
        if pd.notna(smin) and pd.notna(smax):
            return f"\u00a3{int(smin):,} – \u00a3{int(smax):,}"
        if pd.notna(smin):
            return f"\u00a3{int(smin):,}"
        if pd.notna(smax):
            return f"\u00a3{int(smax):,}"
        return ""

    df["salary"] = df.apply(_fmt_salary, axis=1)
    return df


@st.cache_data(ttl=60)
def load_run_logs() -> pd.DataFrame:
    conn = _get_conn()
    try:
        df = pd.read_sql_query("SELECT * FROM run_log ORDER BY id DESC", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["per_source"] = df["per_source"].apply(lambda x: json.loads(x) if x else {})
    return df


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df_jobs = load_jobs()
df_runs = load_run_logs()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("\U0001F50D Filters")

    search_text = st.text_input("Search", placeholder="e.g. Software Engineer London")

    score_range = st.slider("Match Score", 0, 100, (0, 100))

    if not df_jobs.empty:
        available_sources = sorted(df_jobs["source"].unique())
        selected_sources = st.multiselect("Sources", available_sources, default=available_sources)

        available_locations = sorted(df_jobs["location"].dropna().unique())
        selected_locations = st.multiselect("Locations", available_locations)

        visa_filter = st.radio("Visa Sponsorship", ["All", "Visa Only", "No Visa Flag"])
    else:
        selected_sources = []
        selected_locations = []
        visa_filter = "All"

    st.divider()
    st.subheader("Your Profile")

    from src.cv_parser import (
        extract_text,
        extract_profile,
        save_profile,
        load_profile,
    )
    from src.preferences import (
        load_preferences,
        save_preferences,
        get_empty_preferences,
    )
    from src.filters.skill_matcher import reload_profile
    from src.config.settings import CV_PROFILE_PATH, USER_PREFERENCES_PATH

    # --- Tab layout for the three input layers ---
    cv_tab, prefs_tab, linkedin_tab = st.tabs(["CV", "Preferences", "LinkedIn"])

    # ---- TAB 1: CV Upload ----
    with cv_tab:
        uploaded_cv = st.file_uploader(
            "Upload CV (PDF/DOCX)",
            type=["pdf", "docx"],
            key="cv_upload",
            help="Upload your CV to personalise job matching. "
            "Skills are extracted automatically.",
        )

        if uploaded_cv is not None:
            suffix = Path(uploaded_cv.name).suffix
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            try:
                os.write(tmp_fd, uploaded_cv.getvalue())
                os.close(tmp_fd)
                text = extract_text(tmp_path)
                profile = extract_profile(text)
                profile["source_file"] = uploaded_cv.name
                save_profile(profile)
                reload_profile()
                total_skills = (
                    len(profile["primary_skills"])
                    + len(profile["secondary_skills"])
                    + len(profile["tertiary_skills"])
                )
                st.success(
                    f"Extracted {total_skills} skills from **{uploaded_cv.name}**"
                )
                st.cache_data.clear()
                st.rerun()
            except (ValueError, FileNotFoundError) as exc:
                st.error(f"Failed to process CV: {exc}")
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        _cv_profile = load_profile()
        if _cv_profile:
            st.success(f"Active: {_cv_profile.get('source_file', 'unknown')}")
            st.caption(f"Extracted: {_cv_profile.get('extracted_at', 'N/A')}")
            with st.expander("CV Skills Profile"):
                for label, key in [
                    ("Job Titles", "job_titles"),
                    ("Primary Skills", "primary_skills"),
                    ("Secondary Skills", "secondary_skills"),
                    ("Tertiary Skills", "tertiary_skills"),
                    ("Locations", "locations"),
                ]:
                    items = _cv_profile.get(key, [])
                    st.write(f"**{label} ({len(items)}):** {', '.join(items) if items else 'None'}")
            if st.button("Reset CV Profile", use_container_width=True):
                CV_PROFILE_PATH.unlink(missing_ok=True)
                reload_profile()
                st.cache_data.clear()
                st.rerun()
        else:
            st.info("No CV uploaded yet.")

    # ---- TAB 2: Preferences ----
    with prefs_tab:
        st.caption("Add info beyond your CV — titles you'd accept, skills you know, etc.")
        _prefs = load_preferences() or get_empty_preferences()

        pref_titles = st.text_area(
            "Job Titles (one per line)",
            value="\n".join(_prefs.get("job_titles", [])),
            height=80,
            key="pref_titles",
            help="Roles you'd consider, e.g. 'AI Platform Engineer', 'Cloud ML Engineer'",
        )
        pref_skills = st.text_area(
            "Skills (one per line)",
            value="\n".join(_prefs.get("skills", [])),
            height=80,
            key="pref_skills",
            help="Skills you have but may not be on your CV, e.g. 'Azure', 'GCP'",
        )
        pref_locations = st.text_area(
            "Locations (one per line)",
            value="\n".join(_prefs.get("locations", [])),
            height=60,
            key="pref_locations",
            help="Where you'd like to work, e.g. 'Remote', 'London', 'Berlin'",
        )
        pref_about = st.text_area(
            "About Me",
            value=_prefs.get("about_me", ""),
            height=80,
            key="pref_about",
            help="Brief career objective or personal summary",
        )
        pref_projects = st.text_area(
            "Projects (one per line)",
            value="\n".join(_prefs.get("projects", [])),
            height=80,
            key="pref_projects",
            help="Notable projects you've worked on",
        )
        pref_certs = st.text_area(
            "Certifications / Licenses (one per line)",
            value="\n".join(_prefs.get("certifications", [])),
            height=60,
            key="pref_certs",
            help="e.g. 'AWS Solutions Architect', 'PMP', 'CKA'",
        )

        if st.button("Save Preferences", use_container_width=True, type="primary"):
            new_prefs = {
                "job_titles": [t.strip() for t in pref_titles.strip().split("\n") if t.strip()],
                "skills": [s.strip() for s in pref_skills.strip().split("\n") if s.strip()],
                "locations": [l.strip() for l in pref_locations.strip().split("\n") if l.strip()],
                "about_me": pref_about.strip(),
                "projects": [p.strip() for p in pref_projects.strip().split("\n") if p.strip()],
                "certifications": [c.strip() for c in pref_certs.strip().split("\n") if c.strip()],
            }
            # Preserve LinkedIn data if it was imported
            if _prefs.get("linkedin"):
                new_prefs["linkedin"] = _prefs["linkedin"]
            save_preferences(new_prefs)
            reload_profile()
            st.cache_data.clear()
            st.success("Preferences saved!")
            st.rerun()

        if load_preferences():
            if st.button("Clear Preferences", use_container_width=True):
                USER_PREFERENCES_PATH.unlink(missing_ok=True)
                reload_profile()
                st.cache_data.clear()
                st.rerun()

    # ---- TAB 3: LinkedIn Import ----
    with linkedin_tab:
        st.caption(
            "Import your LinkedIn data export (ZIP) for comprehensive profile data. "
            "Download from LinkedIn: Settings > Data Privacy > Get a copy of your data."
        )
        uploaded_linkedin = st.file_uploader(
            "Upload LinkedIn Export (ZIP)",
            type=["zip"],
            key="linkedin_upload",
        )

        if uploaded_linkedin is not None:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip")
            try:
                os.write(tmp_fd, uploaded_linkedin.getvalue())
                os.close(tmp_fd)
                from src.linkedin_import import parse_linkedin_zip
                li_data = parse_linkedin_zip(tmp_path)
                # Store LinkedIn data inside preferences
                prefs_current = load_preferences() or get_empty_preferences()
                prefs_current["linkedin"] = li_data
                save_preferences(prefs_current)
                reload_profile()
                st.success(
                    f"LinkedIn imported: {len(li_data.get('job_titles', []))} titles, "
                    f"{len(li_data.get('skills', []))} skills, "
                    f"{len(li_data.get('certifications', []))} certifications"
                )
                st.cache_data.clear()
                st.rerun()
            except (ValueError, FileNotFoundError) as exc:
                st.error(f"Failed to process LinkedIn export: {exc}")
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        # Show LinkedIn data if imported
        _prefs_li = load_preferences()
        if _prefs_li and _prefs_li.get("linkedin"):
            li = _prefs_li["linkedin"]
            with st.expander("LinkedIn Data"):
                for label, key in [
                    ("Job Titles", "job_titles"),
                    ("Skills", "skills"),
                    ("Locations", "locations"),
                    ("Certifications", "certifications"),
                    ("Companies", "companies"),
                    ("Education", "education"),
                    ("Projects", "projects"),
                ]:
                    items = li.get(key, [])
                    if items:
                        st.write(f"**{label} ({len(items)}):** {', '.join(items[:20])}")
            if st.button("Remove LinkedIn Data", use_container_width=True):
                _prefs_li.pop("linkedin", None)
                save_preferences(_prefs_li)
                reload_profile()
                st.cache_data.clear()
                st.rerun()
        else:
            st.info("No LinkedIn data imported yet.")

    # ---- Merged Profile Summary ----
    st.divider()
    from src.filters.skill_matcher import _load_active_profile
    _merged = _load_active_profile()
    _has_cv = load_profile() is not None
    _has_prefs = load_preferences() is not None
    _sources = []
    if _has_cv:
        _sources.append("CV")
    if _has_prefs:
        _sources.append("Preferences")
        if (load_preferences() or {}).get("linkedin"):
            _sources.append("LinkedIn")
    if _sources:
        st.caption(f"Active sources: {', '.join(_sources)}")
        with st.expander("Merged Profile"):
            st.write(f"**Job Titles ({len(_merged.get('job_titles', []))}):** "
                     f"{', '.join(_merged.get('job_titles', [])[:15]) or 'None'}")
            st.write(f"**Primary Skills ({len(_merged.get('primary_skills', []))}):** "
                     f"{', '.join(_merged.get('primary_skills', [])[:15]) or 'None'}")
            st.write(f"**Secondary Skills ({len(_merged.get('secondary_skills', []))}):** "
                     f"{', '.join(_merged.get('secondary_skills', [])[:15]) or 'None'}")
            st.write(f"**Tertiary Skills ({len(_merged.get('tertiary_skills', []))}):** "
                     f"{', '.join(_merged.get('tertiary_skills', [])[:15]) or 'None'}")
            st.write(f"**Locations ({len(_merged.get('locations', []))}):** "
                     f"{', '.join(_merged.get('locations', [])) or 'None'}")
    else:
        st.info("No profile data. Upload a CV or set preferences to personalise your search.")

    if _has_cv or _has_prefs:
        if st.button("Reset Everything", use_container_width=True):
            CV_PROFILE_PATH.unlink(missing_ok=True)
            USER_PREFERENCES_PATH.unlink(missing_ok=True)
            reload_profile()
            st.cache_data.clear()
            st.rerun()

    st.divider()
    st.subheader("\u2699\uFE0F Actions")
    trigger_search = st.button("\U0001F680 Run New Search", use_container_width=True)
    export_csv = st.button("\U0001F4E5 Export CSV", use_container_width=True)

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
df_filtered = df_jobs.copy()

if not df_filtered.empty:
    # Text search across title, company, location, description
    if search_text:
        q = search_text.lower()
        mask = (
            df_filtered["title"].str.lower().str.contains(q, na=False)
            | df_filtered["company"].str.lower().str.contains(q, na=False)
            | df_filtered["location"].str.lower().str.contains(q, na=False)
            | df_filtered["description"].str.lower().str.contains(q, na=False)
        )
        df_filtered = df_filtered[mask]

    # Score range
    df_filtered = df_filtered[
        (df_filtered["match_score"] >= score_range[0])
        & (df_filtered["match_score"] <= score_range[1])
    ]

    # Source filter
    if selected_sources:
        df_filtered = df_filtered[df_filtered["source"].isin(selected_sources)]

    # Location filter
    if selected_locations:
        df_filtered = df_filtered[df_filtered["location"].isin(selected_locations)]

    # Visa filter
    if visa_filter == "Visa Only":
        df_filtered = df_filtered[df_filtered["visa_flag"]]
    elif visa_filter == "No Visa Flag":
        df_filtered = df_filtered[~df_filtered["visa_flag"]]

# ---------------------------------------------------------------------------
# Trigger new search
# ---------------------------------------------------------------------------
if trigger_search:
    with st.spinner("Running Job360 search... this may take 2-3 minutes."):
        result = subprocess.run(
            [sys.executable, "-m", "src.main"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=300,
        )
    if result.returncode == 0:
        st.success("Search complete! Refreshing data...")
        st.cache_data.clear()
        st.rerun()
    else:
        st.error(f"Search failed:\n```\n{result.stderr[-1000:]}\n```")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("\U0001F4BC Job360 Dashboard")
st.caption("Personalised Job Search Aggregator — Powered by Your CV, Preferences & LinkedIn")

# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------
if df_jobs.empty:
    st.info(
        "No jobs in the database yet. Click **Run New Search** in the sidebar to get started!"
    )
    st.stop()

# ---------------------------------------------------------------------------
# KPI metrics
# ---------------------------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Jobs", len(df_filtered))
c2.metric("Avg Score", f"{df_filtered['match_score'].mean():.0f}" if len(df_filtered) else "—")
c3.metric("Top Score", int(df_filtered["match_score"].max()) if len(df_filtered) else "—")
c4.metric("Visa Sponsors", int(df_filtered["visa_flag"].sum()) if len(df_filtered) else 0)
c5.metric("Sources", df_filtered["source"].nunique() if len(df_filtered) else 0)

st.divider()

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
chart_left, chart_right = st.columns(2)

with chart_left:
    if len(df_filtered):
        fig_hist = px.histogram(
            df_filtered,
            x="match_score",
            nbins=20,
            color_discrete_sequence=["#1a73e8"],
            title="Score Distribution",
            labels={"match_score": "Match Score", "count": "Jobs"},
        )
        fig_hist.add_vline(
            x=MIN_MATCH_SCORE,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Min ({MIN_MATCH_SCORE})",
        )
        fig_hist.update_layout(bargap=0.1, height=350)
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("No data to chart.")

with chart_right:
    if len(df_filtered):
        source_counts = df_filtered["source"].value_counts().reset_index()
        source_counts.columns = ["source", "count"]
        fig_pie = px.pie(
            source_counts,
            values="count",
            names="source",
            title="Jobs by Source",
            hole=0.35,
        )
        fig_pie.update_layout(height=350)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No data to chart.")

st.divider()

# ---------------------------------------------------------------------------
# Job listings table
# ---------------------------------------------------------------------------
st.subheader(f"Job Listings ({len(df_filtered)})")

if len(df_filtered):
    display_cols = [
        "match_score", "title", "company", "location",
        "salary", "source", "visa_flag", "date_found", "apply_url",
    ]
    df_display = df_filtered[display_cols].copy()
    df_display = df_display.rename(columns={
        "match_score": "Score",
        "title": "Title",
        "company": "Company",
        "location": "Location",
        "salary": "Salary",
        "source": "Source",
        "visa_flag": "Visa",
        "date_found": "Date",
        "apply_url": "Apply",
    })

    st.dataframe(
        df_display,
        use_container_width=True,
        height=500,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d"
            ),
            "Visa": st.column_config.CheckboxColumn("Visa"),
            "Apply": st.column_config.LinkColumn("Apply", display_text="Apply"),
            "Date": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
        },
        hide_index=True,
    )
else:
    st.info("No jobs match the current filters.")

# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
if export_csv and len(df_filtered):
    csv_data = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CSV",
        data=csv_data,
        file_name=f"job360_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------
with st.expander("Run History", expanded=False):
    if not df_runs.empty:
        col_a, col_b = st.columns(2)

        with col_a:
            st.dataframe(
                df_runs[["timestamp", "total_found", "new_jobs"]].rename(columns={
                    "timestamp": "Time",
                    "total_found": "Total Found",
                    "new_jobs": "New Jobs",
                }),
                use_container_width=True,
                hide_index=True,
            )

        with col_b:
            if len(df_runs) > 1:
                fig_line = px.line(
                    df_runs.sort_values("timestamp"),
                    x="timestamp",
                    y="new_jobs",
                    title="New Jobs per Run",
                    markers=True,
                )
                fig_line.update_layout(height=300)
                st.plotly_chart(fig_line, use_container_width=True)

        # Per-source breakdown of latest run
        if len(df_runs):
            latest = df_runs.iloc[0]
            ps = latest["per_source"]
            if ps:
                st.subheader("Latest Run — Per Source")
                ps_df = pd.DataFrame(
                    list(ps.items()), columns=["Source", "Jobs Found"]
                ).sort_values("Jobs Found", ascending=False)
                fig_bar = px.bar(
                    ps_df, x="Source", y="Jobs Found",
                    color_discrete_sequence=["#34a853"],
                )
                fig_bar.update_layout(height=300)
                st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No runs recorded yet.")

# ---------------------------------------------------------------------------
# Previous exports
# ---------------------------------------------------------------------------
with st.expander("Previous Exports", expanded=False):
    exports_path = Path(EXPORTS_DIR)
    if exports_path.exists():
        csv_files = sorted(exports_path.glob("*.csv"), reverse=True)
        if csv_files:
            for f in csv_files[:10]:
                col_f, col_d = st.columns([3, 1])
                col_f.text(f.name)
                with open(f, "rb") as fh:
                    col_d.download_button(
                        "Download", fh.read(), file_name=f.name, mime="text/csv",
                        key=f"dl_{f.name}",
                    )
        else:
            st.info("No exports yet.")
    else:
        st.info("Exports directory not found.")
