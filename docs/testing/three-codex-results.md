# 三 Codex 汽车实验报告（迭代中）

本文保留V4冻结结果，第二轮覆盖改进和冷链路计时仍在运行；没有把第二轮写成通过。规范见 [three-codex-acceptance.md](three-codex-acceptance.md)。

## 角色与盲测

C1开发通用产品、冻结原文基准、修复和审计；C2仅经公开API编写领域数据及建库，不改固定Schema、迁移或代码；C3只读发布知识，不读源文件、C2资产或私有基准。C2/C3使用独立原生Codex会话和外层OS隔离。

C2初始围绕6个代表问题检查建库目标，另做2类实际图用例及条件正反向；这不是独立问答验收。C3原12题有6题未提供给C2，追加24题全部未提供给C2，共36题、30题对C2保留。追加测试期间V4冻结，未按新题补库。

## V4规模与结果

6份数字PDF，67页，1133原文块；116条记录（61对象、29属性断言、26关系）。60个去重对象节点，34个有连边节点，26条去重边。领域配置为12类对象、24个属性、9类关系、9个条件；事件和规则实例为0。

Wiki为1篇记录总览，150个引用均经公开API读取且原文切片/偏移匹配。尚未实现多篇主题文章组织。

12题基线及权限、条件、图路径、失败恢复和版本固定检查通过。追加24题为18 supported、3 partial、3 insufficient，38条独立引用核对通过。两条要求的图路径缺失；追加题语义覆盖为21 none、3 partial，主要依赖原文检索。不能据此宣称完整汽车语义库或通用性已成立。

## 第一窗口代码与固定结构

统计为当前物理行/非空行，不是编辑键数或逻辑LOC；模型、外部MinerU、wheel、生成JSON和C2领域资产不计入。

| 类别 | 文件数 | 物理行 | 非空行 |
|---|---:|---:|---:|
| product_python | 31 | 1871 | 1670 |
| migrations_sql | 8 | 47 | 47 |
| workspace_launcher | 1 | 11 | 10 |
| tests_python | 17 | 1011 | 857 |
| scripts_python | 20 | 576 | 550 |


固定物理表共17张：`schema_migrations`, `knowledge_bases`, `domain_versions`, `source_versions`, `source_withdrawals`, `parse_versions`, `source_blocks`, `records`, `evidence_links`, `builds`, `releases`, `tasks`, `review_decisions`, `search_documents`, `feedback`, `onboarding`, `source_search_documents`。

`records`承载object/assertion/relation/event/rule五种通用记录；没有为每个汽车字段建专表。图是固定发布版的relation记录投影，用递归SQL查询；预置汽车表0张、预置汽车图0份。产品、模板、迁移和最小示例的汽车专名扫描无命中，固定领域Schema及迁移在测试期间无C2修改。汽车词汇仅位于领域数据、知识库和测试材料。

## 时间的统计口径

原生Codex日志可还原每次MCP调用起止和耗时，以及每轮会话耗时。旧批次有多题共享调用，不能将批次时长平均摊成单题延迟；历史未采集的worker内部阶段不填估计值。

新一轮开启通用阶段计时：导入、冷解析/缓存、领域分析、模型抽取、核验、语义向量、原文向量、Wiki、发布，以及检索中的模型规划、SQL/向量、图查询和读证据。异步任务提交耗时不等于任务完成时间；父子阶段不可重复求和。完整逐步时间表将在本轮结束后追加。

## 限制

这是AI参考基准和AI复核，不是人工专家验收；只有一个领域，不是三领域通用性结论。未验收扫描件OCR、生产安全、稳定性能或计费上限。原文问答、语义表覆盖与图覆盖分别报告。
