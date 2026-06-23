# JAYA_CORE Production Release Checklist

## Objective
Checklist operasional untuk mendorong JAYA_CORE dari kandidat produksi menjadi release candidate yang siap divalidasi manusia.

## Required Automated Evidence
- [x] Runtime observability gate passes.
- [x] Core JayaIR gate passes.
- [x] Architecture boundary gate passes.
- [x] Phase 2 safety gates pass.
- [x] Strict benchmark gate passes.
- [x] `IronEngine.healthcheck()` returns contract shape in automated tests.
- [x] `IronEngine.readiness_report()` returns production-candidate shape in automated tests.

## Required Human Evidence
- [ ] Technical lead sign-off completed.
- [ ] Architecture sign-off completed.
- [ ] Performance sign-off completed.
- [ ] Security sign-off completed.
- [ ] Deployment validation on target machine documented.

## Release Procedure
1. Run all automated gates.
2. Capture benchmark snapshot JSON.
3. Fill `PHASE1_SIGNOFF_TEMPLATE.md` or update sign-off draft.
4. Review `PRODUCTION_READINESS.md` and attach blocker status.
5. Approve or reject candidate explicitly.

## Rollback Readiness
- [ ] Previous stable commit SHA documented.
- [x] Rollback command/procedure documented.
- [ ] Runtime degraded mode behavior verified.

## Notes
This checklist does not replace human approval; it makes the evidence package executable and auditable.

Supporting docs:
- `JAYA_CORE/docs/DEPLOYMENT_VALIDATION_CHECKLIST.md`
- `JAYA_CORE/docs/ROLLBACK_PLAN.md`

## Latest Automated Evidence Snapshot
- Core JayaIR gate: PASS
- Benchmark guard + architecture boundary: PASS
- Phase 2 evolution/rollback/manifest gates: PASS
- Strict benchmark gate: PASS
- Runtime observability, healthcheck, readiness contract gate: PASS
