# PDF information preservation implementation plan

**Goal:** Preserve document units and explicitly expose parse gaps; extract structured table rows without silently losing headers, symbols or media.

**Architecture:** Keep immutable upstream JSON. Normalize document units and coverage separately; persist them on parse_versions using additive columns. Text-bearing units become evidence blocks; unresolved media stay in units and coverage, never fabricated as facts. Local native PDF text supplements empty equation regions and layout tables where defensible. All capabilities remain generic.

**Spec:** docs/validation/ragflow-pdf-reference-2026-11-02.md and the user's approval to improve.

## Constraints and decisions
- C1 never reads automotive raw or benchmark. Synthetic fixtures only.
- Continue in the existing product-development branch; preserve unrelated .DS_Store files and external running actors. No additional service/model or document upload.
- Prior advice and user approval authorize implementation; no new approval round.
- Native layout table recovery is parser-derived structure, not verified semantic truth. Never infer missing cells or repeat values for covered cells without metadata.
- This increment does not claim OCR/VLM integration or mathematical evaluation. Missing media remain visible.

## Tasks
1. Write failing tests for document units, row/header preservation, empty media, source immutability, superscripts and coverage. Implement normalization and bounded layout-table recovery.
2. Persist units/coverage, expose producer-only source parse report through MCP, select parser-version-compatible cache and retain old versions. Test DB persistence and cache selection.
3. Connect local native text supplement, extraction row completeness instructions, pipeline coverage reporting and atomic row batching. Test omission reporting and no silent splitting.
4. Run targeted/full regressions and real synthetic PDF + DeepSeek extraction; compare table row recovery, missing media and support problems. Record limits and timings. Obtain final code review before commit.

## Review focus
Empty-only documents remain unprocessable as factual text but retain diagnostics; page numbering and bbox stay authentic; native fallback failure is explicit; captions cannot hide cell content; inferred table structure does not certify semantic attribution.

## Execution ledger
- Tasks 1–3 implemented in place on the existing prototype branch; no raw automotive or benchmark reads.
- RED: 5 normalization tests failed before implementation; parser persistence/version tests failed before migration/API changes; row batching and structured-unit grounding tests failed before fixes; published coverage test failed before manifest addition.
- Ruling: do not generate quantity prose from arbitrary parenthesized header suffixes. Preserve original header/cells; match requested domain units to the same column only during lexical grounding.
- Reviewer found manufactured suffix units and page-global recovery suppression. Both corrected and regression-tested; final re-review requested.
- Additive migration 009 keeps the same physical table count and generic semantic kinds.
- Consumer-visible build coverage and Wiki warnings added; producer-only unit bodies are not exported in manifest.
- Task 4 complete: full suite 143 passed; real synthetic PDF/DeepSeek run and final no-embedding rebuild recorded in pdf-improvement-results report and external final-result.json. Native layout facts deliberately remain review-required, not silently published.
- Final review: no remaining blockers. Ruling: inferred-layout facts cannot bypass review via source baseline indexing; regression test added. OCR/VLM and complete table/footnote semantics remain explicit future work, not completion claims.
