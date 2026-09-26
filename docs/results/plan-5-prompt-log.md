# Plan 5 prompt log: S4's prompts after the first smoke run

Every prompt edit after the first S4 smoke run, with its reason and result (parity rule: the same tuning effort is
offered to S1b). Format of `plan-4a-prompt-log.md`.

## D2 (2026-09-25): the document brief

- **What changed.** With the router on, an Investigator gets a document brief (`panel_prompts.doc_brief`) instead of
  an issue brief: one document, its pages as the reading budget, and for each open issue it may settle the same lines
  the issue brief carries (belief or committed value, the engine's flip amount, any objection). It ends "Report every
  issue type this document settles, including ones not listed." The issue brief's wording is unchanged (its lines
  moved into `_about`).
- **Why.** The page-spend audit of the `c989fb1` runs: S4 never opened the audited notes (0 of 10), and Investigators
  kept reading after finding their answer. Spec: `docs/superpowers/specs/2026-09-25-doc-router-design.md`.
- **Budget sentence (final review).** The brief's budget is the document's pages plus one unit (capped at what is
  left), so a search first still leaves enough to open the document; the brief states that budget.
- **Parity.** An S4 architecture change, not added knowledge: the brief states only the record and the engine's
  numbers, and the router's weights use only the diligence map's order that S1b's guide already states. S1b's prompt
  is unchanged.
- **Result.** See `plan-5-dev-checks.md` (the D2 re-run).

## Freeze (2026-09-26)

S4 frozen with its prompts as above (tag `s4-frozen-plan5`). Task 6 Step 3's tuning loop was skipped (see
`plan-5-dev-checks.md`), so no tuning edits were made, and none were offered to S1b.
