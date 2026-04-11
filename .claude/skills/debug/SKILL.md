# /debug — Unified Debugging

**Methodology: CRIIVP** — Capture → Reproduce → Isolate → Implement → Verify → Prevent

One command to investigate scoring, logs, notifications, and deduplication with structured root-cause analysis.

## Usage

```
/debug <target> [args...]
```

## Targets

| Target | Args | What It Does |
|--------|------|-------------|
| `score` | `<title> <company>` | Trace scoring breakdown for a job |
| `logs` | `[source] [severity]` | Analyze log files for error patterns |
| `notify` | `<channel>` | Send test notification to verify configuration |
| `dedup` | `<title> <company>` | Trace deduplication for a job |

## Instructions

### Target: `score`

**Capture** the full component-by-component scoring breakdown:

```bash
python -c "
from src.profile.storage import load_profile
from src.profile.keyword_generator import generate_search_config
from src.filters.skill_matcher import JobScorer

profile = load_profile()
if not profile:
    print('ERROR: No profile loaded. Run setup-profile first.')
    exit(1)

config = generate_search_config(profile)
scorer = JobScorer(config)
title = '<TITLE_ARG>'
company = '<COMPANY_ARG>'
print(f'Scoring: \"{title}\" @ {company}')
print(f'Config: {len(config.job_titles)} titles, {len(config.primary_skills)}P/{len(config.secondary_skills)}S/{len(config.tertiary_skills)}T skills')
print()

# Component breakdown table
title_lower = title.lower()
print('COMPONENT BREAKDOWN')
print('=' * 50)

# Title component (0-40)
title_matches = [jt for jt in config.job_titles if jt.lower() in title_lower]
title_score = 40 if any(jt.lower() == title_lower for jt in config.job_titles) else (20 if title_matches else 0)
print(f'  Title (0-40):    {title_score}')
for jt in title_matches:
    print(f'    matched: \"{jt}\"')
if not title_matches:
    print(f'    no match in {len(config.job_titles)} titles')

# Negative check
neg_matches = [neg for neg in config.negative_title_keywords if neg.lower() in title_lower]
neg_penalty = -30 if neg_matches else 0
if neg_matches:
    print(f'  Negative:       {neg_penalty}')
    for neg in neg_matches:
        print(f'    matched: \"{neg}\"')

# Skills component (0-40) — cannot trace without description
print(f'  Skills (0-40):   [needs job description to trace]')

# Location component (0-10) — cannot trace without location
print(f'  Location (0-10): [needs job location to trace]')

# Recency component (0-10) — cannot trace without date
print(f'  Recency (0-10):  [needs job date to trace]')

print()
estimated = title_score + neg_penalty
print(f'Estimated from title alone: {estimated}/100')
if estimated < 30:
    print(f'  Below MIN_MATCH_SCORE=30 — WHY: title did not match any of {len(config.job_titles)} configured titles')
print()
print('For full scoring, use the dashboard or run the pipeline.')
"
```

Replace `<TITLE_ARG>` and `<COMPANY_ARG>` with the user's arguments. If the score is surprising, **explain WHY** based on the component breakdown.

### Target: `logs`

**Capture** and **categorize** log errors by type, not just source:

```bash
python -c "
from pathlib import Path
import re
from collections import Counter

log_dir = Path('data/logs')
if not log_dir.exists():
    print('No logs directory found.')
    exit(0)

log_files = list(log_dir.glob('*.log'))
if not log_files:
    print('No log files found.')
    exit(0)

# Error categories
CATEGORIES = {
    'Network': ['ConnectionError', 'TimeoutError', 'ClientError', 'aiohttp'],
    'Auth': ['401', '403', 'Unauthorized', 'Forbidden', 'API key'],
    'Parse': ['JSONDecodeError', 'KeyError', 'IndexError', 'TypeError', 'ValueError'],
    'Rate limit': ['429', 'rate limit', 'Too Many Requests', 'throttl'],
}

for lf in log_files:
    text = lf.read_text(errors='ignore')
    lines = text.strip().split('\n')
    errors = [l for l in lines if '[ERROR]' in l or '[WARNING]' in l]
    print(f'{lf.name}: {len(lines)} lines, {len(errors)} errors/warnings')

    if errors:
        # Categorize errors
        categorized = Counter()
        uncategorized = []
        for e in errors:
            matched = False
            for cat, patterns in CATEGORIES.items():
                if any(p.lower() in e.lower() for p in patterns):
                    categorized[cat] += 1
                    matched = True
                    break
            if not matched:
                uncategorized.append(e)
                categorized['Other'] += 1

        print('  By category:')
        for cat, cnt in categorized.most_common():
            print(f'    {cat}: {cnt}')

        # Top 3 with root cause + fix + prevention
        print()
        print('  Top 3 errors (root cause + fix + prevention):')
        for i, e in enumerate(errors[-3:], 1):
            print(f'    {i}. {e[:150]}')
            for cat, patterns in CATEGORIES.items():
                if any(p.lower() in e.lower() for p in patterns):
                    if cat == 'Network':
                        print(f'       Root cause: Network/connection failure')
                        print(f'       Fix: Check internet, verify URL, add retry logic')
                        print(f'       Prevention: Use session retry adapter')
                    elif cat == 'Auth':
                        print(f'       Root cause: Authentication/authorization failure')
                        print(f'       Fix: Check API key in .env, verify key is valid')
                        print(f'       Prevention: Validate API key at source init')
                    elif cat == 'Parse':
                        print(f'       Root cause: Unexpected response format')
                        print(f'       Fix: Check API response, add defensive parsing')
                        print(f'       Prevention: Use .get() with defaults, add try/except')
                    elif cat == 'Rate limit':
                        print(f'       Root cause: Rate limit exceeded')
                        print(f'       Fix: Increase delay in RATE_LIMITS, reduce concurrency')
                        print(f'       Prevention: Respect Retry-After headers')
                    break
"
```

If the user provides `[source]` or `[severity]`, filter the output accordingly.

### Target: `notify`

Send a test notification to verify configuration:

```bash
python -c "
import asyncio

channel = '<CHANNEL_ARG>'  # slack, discord, or email

if channel == 'slack':
    from src.notifications.slack_notify import SlackChannel
    ch = SlackChannel()
elif channel == 'discord':
    from src.notifications.discord_notify import DiscordChannel
    ch = DiscordChannel()
elif channel == 'email':
    from src.notifications.email_notify import EmailChannel
    ch = EmailChannel()
else:
    print(f'Unknown channel: {channel}')
    print('Supported: slack, discord, email')
    exit(1)

if not ch.is_configured():
    print(f'{channel}: NOT CONFIGURED (missing env vars)')
    exit(1)

print(f'{channel}: configured, sending test...')
test_jobs = []
test_stats = {'total_found': 0, 'new_jobs': 0, 'sources_queried': 0}
try:
    asyncio.run(ch.send(test_jobs, test_stats))
    print(f'{channel}: SUCCESS')
except Exception as e:
    print(f'{channel}: FAILED — {e}')
"
```

Replace `<CHANNEL_ARG>` with the user's argument.

### Target: `dedup`

**Capture** the dedup key and **query the database** for existing matches:

```bash
python -c "
import sqlite3
from pathlib import Path
from src.models import Job

title = '<TITLE_ARG>'
company = '<COMPANY_ARG>'

job = Job(
    title=title,
    company=company,
    location='',
    apply_url='https://example.com',
    source='debug',
    date_found='2024-01-01',
)

norm_company, norm_title = job.normalized_key()
print(f'Input:  title=\"{title}\", company=\"{company}\"')
print(f'Normalized key: (\"{norm_company}\", \"{norm_title}\")')
print()

# Query actual DB for matches
db = Path('data/jobs.db')
if db.exists():
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        'SELECT title, company, source, date_found FROM jobs WHERE company LIKE ? AND title LIKE ?',
        (f'%{norm_company}%', f'%{norm_title}%')
    ).fetchall()
    if rows:
        print(f'EXISTING MATCHES ({len(rows)} found):')
        for r in rows[:10]:
            print(f'  \"{r[0]}\" @ {r[1]} (source: {r[2]}, date: {r[3]})')
        if len(rows) > 10:
            print(f'  ... and {len(rows) - 10} more')
        print()
        print('These jobs share the same normalized key and would be deduplicated.')
        print('The EARLIEST record is kept; later duplicates are discarded.')
    else:
        print('No existing matches in database — this would be a new job.')
    conn.close()
else:
    print('Database not found — no existing data to check against.')
    print('Jobs with the same normalized key would be deduplicated.')
"
```

Replace `<TITLE_ARG>` and `<COMPANY_ARG>` with the user's arguments.

## Tools Used
Bash, Read, Grep
