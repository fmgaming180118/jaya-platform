# 33 — Pembangunan Pilar 38: Meta Cognitive Planning

- **ID pilar:** 38
- **Tahap:** 9 — Ruang kendali
- **Status saat audit:** NOT_IMPLEMENTED
- **Pemilik:** MODEL, RUNTIME

## Tujuan

Memonitor kemajuan rencana, menguji asumsi, menyesuaikan strategi, dan berhenti
ketika tujuan tercapai atau tidak aman tanpa mengubah objective secara liar.

## Dependensi

- [Pilar 17 — Socratic Mirror](21-p17-socratic-mirror.md)
- [Pilar 18 — Zero Trust](08-p18-zero-trust.md)
- [Pilar 21 — Lingua Logica](02-p21-lingua-logica.md)
- [Pilar 33 — Agentic RAG](30-p33-agentic-rag.md)
- [Pilar 36 — Speculative Reasoning](32-p36-speculative-reasoning.md)

## Kontrak dan integrasi

```text
Goal + plan + observations → progress evaluator → continue/replan/stop/escalate
```

## Checklist implementasi

- [ ] Definisikan goal, invariant, progress metric, budget, dan terminal condition.
- [ ] Pisahkan planner, evaluator, dan execution authority.
- [ ] Validasi replan terhadap ethics, permission, dan remaining budget.
- [ ] Persistensikan plan version, observation, decision, dan rationale.
- [ ] Uji loop, no progress, contradictory goal, tool failure, dan cancellation.
- [ ] Demo menyelesaikan tugas multi-step dengan failure recovery nyata.

## Exit criteria

Planner dapat mengubah strategi tetapi tidak melampaui goal/authority; loop
terbatas dan seluruh step terhubung ke tool serta output aktual.

## Larangan

Daftar langkah buatan model yang tidak dieksekusi bukan meta-planning.
