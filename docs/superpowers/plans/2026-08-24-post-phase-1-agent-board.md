# Post-Phase-1 Planning Agent Board

**Board owner / integrator:** `/root`  
**Branch:** `main`  
**Worktree:** `D:/projects/industrial-reliability-platform`  
**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

This board coordinates documentation planning only. Product implementation remains backlog. Agents share the current worktree but have disjoint file ownership; `.codex/`, `ci-import-fix-report.md`, the Phase 1 worktree, product code, tests, and existing plans are forbidden write scopes.

## Cards

| ID | Owner | State | File scope | Acceptance | Merge gate | Handoff |
|---|---|---|---|---|---|---|
| `plan-early` | `/root/plan_early` | Merged | Phase 1B, 2, 3, 4 plan files | Writing-plans header; exact interfaces/files/tests/commands; Phase 1B fail-closed; downstream champion gate | Placeholder scan, interface review, `git diff --check` | `docs/superpowers/plans/handoffs/2026-08-24-plan-early.md` |
| `plan-middle` | `/root/plan_middle` | Merged | Phase 5, 6, 7, 7A plan files | Alert policy leakage boundary; React real-click E2E; MLflow mandatory; Airflow evidence gate | Placeholder scan, dependency review, `git diff --check` | `docs/superpowers/plans/handoffs/2026-08-24-plan-middle.md` |
| `plan-late` | `/root/plan_late` | Merged | Phase 8, 9, 10A, 10B, 11 plan files | Fault drills; allowlisted RCA; optional-tech decision artifacts; exact-SHA release certification | Placeholder scan, security/risk review, `git diff --check` | `docs/superpowers/plans/handoffs/2026-08-24-plan-late.md` |
| `integrate-plans` | `/root` | Merged | Roadmap spec, board, cross-plan review only | All files exist; names/types/dependencies agree; every phase has a terminal gate | Tests/structure scan, diff review, secret scan, smart commit grouping | This board plus final response |

## Implementation backlog

Implementation cards are intentionally not assigned during planning. Their state is `Blocked` until:

1. this plan set is reviewed and committed;
2. Phase 1B is executed in an isolated worktree;
3. Phase 1B reports `FEASIBLE` and a non-null champion before Phase 2 is moved to `Ready`.

Phases 3-11 remain dependency-ordered. A phase moves from `Backlog` to `Ready` only when the prior phase's exact merge and evidence gate are recorded.

## Review sequence

1. Check plan structure and required headers.
2. Scan for placeholders and vague implementation instructions.
3. Check cross-plan interface names, artifact paths, and phase gates.
4. Check security, leakage, raw-data exclusion, and evidence claims.
5. Run `git diff --check` and repository documentation scans.
6. Stage only the new spec, board, plan, and handoff files.
7. Commit by roadmap segment and push only after all groups pass review.

## Control pane status fields

Each handoff records changed files, validation commands, known blockers, and the next owner action. The board state is evidence-based:

- `Running`: assigned agent is writing only its scoped files.
- `Review`: files and handoff exist; integrator checks are pending.
- `Blocked`: exact blocker and owner action are recorded.
- `Merged`: smart commit exists on the planning branch and the push succeeded.

No shared workflow skill will be extracted from this one planning pass. Reconsider only if the same board pattern succeeds on multiple future phase-planning cycles.
