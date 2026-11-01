# 原型状态：可开始独立窗口试用

产品开发分支：prototype。当前为本地实验原型，不是三领域通用性验收结论。

已验证：59 项自动检查；真实 PostgreSQL 角色和跨库隔离、不可变证据及发布；真实 DeepSeek JSON 与本地 1024 维 Embedding；本地 MinerU 数字 PDF；合成 PDF 经公开 MCP 完成抽取、核验、构建、发布和使用者取证回答。186 份汽车 PDF 指纹复核通过。见 docs/validation/。

第二窗口工作区：runtime/workspaces/developer。图形界面信任工作区并确认 gsm_developer MCP 后，说“我要开始创建知识库”。或在终端执行 `python3 runtime/workspaces/developer/start-codex.py` 使用会话配置启动。第三窗口为 runtime/workspaces/consumer，等待开发者发布后使用。

后台需要本项目 PostgreSQL、Embedding 与 worker。启动和复现见 docs/setup.md；开发者指南 docs/developer-guide.md；使用者指南 docs/consumer-guide.md。项目不更改全局 Codex 配置。

待验收：第二窗口独立引导与汽车建库、第三窗口真实问题、人工金标准及阈值、另外两个领域、扫描件 OCR 和代表性表格。现阶段不能宣称通用性成立。全文/向量基线范围、词面核验的边界见 experiments/protocol.md 与 docs/reference/domain.md。

原始 README.md 作为任务书保留；本文件报告实现状态，不把目标设计写成已完成能力。
