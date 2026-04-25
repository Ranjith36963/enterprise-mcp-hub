---
active: true
iteration: 1
session_id:
max_iterations: 15
completion_promise: "STEP-1.5-GREEN"
started_at: "2026-04-25T00:00:00Z"
---

Implement docs/step_1_5_plan.md in cohorts X→Y→Z. Cohort X persists 9 score-dim columns (S1.1-A,B,C,D) and wires the staleness state machine (S1.5-A,B,C); Cohort Y surfaces dims through the API + ESCO-normalises CV skills + tiers in ProfileResponse; Cohort Z ships GET /profile/versions, POST /profile/versions/{id}/restore, GET /profile/json-resume, GET /notifications, plus 6 new Pydantic models, the ProfileResponse expansion, and JobResponse.dedup_group_ids. Verification gate is `make verify-step-1.5`. Only emit <promise>STEP-1.5-GREEN</promise> after the gate passes including the value-presence assertion (at least one JobResponse has a non-zero dim) and the sentinel `.claude/step-1-5-verified.txt` is written at the green commit.
