# 实施取舍与验收边界

以下记录本轮实施者所作选择及其代价。尚未完成的外部实验不作为产品能力结论。

- Ruling: Fresh project initialized on prototype branch in requested directory rather than creating another checkout — no existing code or branch to protect, and user chose development in this directory — cost if wrong: later isolation requires a worktree.

- Task 1: Ruling: uv response-body downloads timed out while curl worked; downloaded wheels into ignored runtime directory and resolved offline, pinning Python 3.12 as planned. Lock currently targets macOS prototype — portability needs a separate lock resolution before Linux packaging.

- Task 2: Ruling: semantic kinds initially share records table, with typed public validation added in build task — keeps common provenance/version machinery unified; cost if wrong: future specialized query indexes may require migration.

- Ruling: While isolated MinerU dependency installation runs, proceed with task 4's parser-independent semantic validation tests — public parser boundary is defined — cost if wrong: actual PDF schema differences may require adapter changes.

- Task 4: Ruling: Wiki uses deterministic rendering of semantic records with evidence links rather than another LLM generation — guarantees shared values/conditions and no extra model claims — cost if wrong: prose quality is basic.

- Task 4: Ruling: Chinese lexical retrieval uses explicit CJK bigrams with PG simple tokenizer and substring fallback, not default English tokenization — baseline quality still needs human benchmark — cost if wrong: longer queries may have weak recall.

- Task 5: Ruling: profiles are signed with local operator secret to prevent role/scope edits, with separate DB roles; this is service capability isolation, not an OS sandbox against same-user filesystem access — cost if wrong: operator files need real process/user isolation before production.

- Task 6: Ruling: baseline source index currently includes full parse versions referenced by selected semantic records; entirely unextracted source inputs require scope completion before strict same-corpus comparison — cost if wrong: benchmark could unfairly exclude documents, so no comparison claim made.

- Task 6: Ruling: project-scoped MCP config is not loaded before client trusts workspace; added explicit per-session CLI launcher instead of changing global trust — RED missing launcher→GREEN actual launcher test and local Codex config detection — cost if wrong: app still requires user trust before loading project config.

- Final: Ruling: three-domain generality and independent role acceptance remain pending, not claimed complete — requires real external roles and human gold data — cost if wrong: would overstate experiment results.

- Final: Ruling: baseline full-corpus completeness and OCR quality remain explicit limitations — no strict comparison or OCR acceptance claimed — cost if wrong: biased benchmark or unreadable scan evidence.

- Final: Ruling: session launcher configuration is verified, actual app trust and guided second-window behavior remain external acceptance — no global settings modified — cost if wrong: user may need initial client trust/setup correction.

- Final: Ruling: withdrawal affects future support/conflicts, not immutable historical evidence; current authorization still gates historical reads — documented public contract — cost if wrong: a future legal deletion/retention requirement would require a separate design.
