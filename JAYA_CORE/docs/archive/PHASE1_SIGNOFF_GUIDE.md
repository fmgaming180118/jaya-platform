# Phase 1 Sign-Off Guide

## Purpose
Quick procedure for reviewers to complete Phase 1 approval consistently.

## Steps
1. Open and verify technical checklist:
   - `JAYA_CORE/docs/PHASE1_EXIT_CHECKLIST.md`
2. Review governance decisions:
   - `JAYA_CORE/docs/PHASE1_DECISION_LOG.md`
3. Review performance evidence:
   - `JAYA_CORE/docs/phase1_benchmark_report.md`
   - `JAYA_CORE/docs/phase1_benchmark_latest.json`
4. Fill reviewer form:
   - `JAYA_CORE/docs/PHASE1_SIGNOFF_TEMPLATE.md`
   - or start from prefilled draft:
     - `JAYA_CORE/docs/PHASE1_SIGNOFF_DRAFT_2026-03-27.md`
5. Record approval result in project communication channel and attach commit SHA.

## Minimum Approval Rule
Phase 1 can be accepted only if all four reviewer roles approve:
- Technical Lead
- Architecture Reviewer
- Performance Reviewer
- Security Reviewer

## Rejection Rule
If one reviewer rejects:
- mark `PHASE 1 REJECTED`,
- list blocking issues,
- create remediation actions,
- rerun checklist and sign-off after fixes.
