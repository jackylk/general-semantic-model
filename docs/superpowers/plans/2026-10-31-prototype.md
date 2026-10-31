# 通用语义模型原型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让第二窗口从“我要开始创建知识库”进入引导，通过公开合同建库，再由第三窗口检索固定发布版本及原文证据。

**Architecture:** Python 服务共用类型化业务层，开发者与使用者 MCP 分别暴露能力。PostgreSQL 保存通用语义记录及版本，本地内容寻址仓库保存原件与解析结构；关系表派生图，所有消费绑定发布版本。

**Tech Stack:** Python 3.12、uv、Pydantic、psycopg、PostgreSQL 17、pgvector、MCP Python SDK、pytest；版本安装时锁定。

**Spec:** `docs/superpowers/specs/2026-10-31-prototype-design.md`

## Global Constraints

- 第二窗口不读产品内部实现、不直接修表、不修改产品代码。
- “我要开始创建知识库”是引导与角色验收起点。
- 不连接 dbay.cloud，不修改其他项目、生产服务或既有数据库容器。
- 核心代码不得包含汽车专用模型或查询分支。
- 真实模型缺配置时报告阻塞，不能用 mock 冒充实验结果。
- 第二、第三领域尚未选定；未完成三领域不能宣称通用性验证完成。
- 不提交凭据、原始大文件、模型权重、本地运行数据。

## Review Focus

- 中文数量、单位与缺失条件：不得丢失精度或补出未给出的条件（任务 1、4）。
- 同名不同配置及跨来源重复对象：不错误合并，支持依据不被单源撤回清空（任务 2、4）。
- 路径穿越、跨库 ID、旧权限：原件和派生查询都拒绝越权（任务 2、5）。
- 模型超时、错误 JSON 和任务重试：预算有界、状态可恢复且不重复发布（任务 3、4）。
- 新窗口与中断恢复：启动入口可发现，不依赖聊天记忆和源码（任务 6）。

## Task 1：领域定义与公开规范

**Files:** `pyproject.toml`、`src/gsm/domain.py`、`src/gsm/errors.py`、`docs/reference/domain.md`、`examples/minimal/domain.yaml`、`tests/test_domain.py`。

**Interfaces:** `validate_domain(data: dict) -> DomainDefinition`；`DomainDefinition` 包含 schema_version、types、properties、relations、events、rules、identity、conditions、policies；`ProductError(code, message, details, retryable)` 为统一错误。

- [ ] 初始化独立 Git 仓库及忽略规则；不改已有 README 任务书；建立 uv 项目和锁文件。
- [ ] 写失败测试：拒绝未知类型引用、重复 ID、非法条件操作、任意执行字段；Decimal 数量可无损往返；缺失条件保留未知；使用非汽车示例。
- [ ] 运行 `uv run pytest tests/test_domain.py -q` 确认预期失败。
- [ ] 实现类型化定义及纯声明式条件 AST，导出 JSON Schema、错误字段路径；示例和文档使用相同校验器。
- [ ] 同命令通过后显式暂存任务文件并提交。

## Task 2：数据库、来源、证据与发布

**Files:** `compose.yaml`、`.env.example`、`migrations/001_core.sql`、`src/gsm/config.py`、`src/gsm/store.py`、`src/gsm/auth.py`、`src/gsm/sources.py`、`src/gsm/releases.py`、`tests/integration/test_store.py`。

**Interfaces:** `Principal(role, kb_ids)`；`Store.transaction(principal, kb_id)`；`SourceService.import_file(principal, kb_id, relative_path)`；`ReleaseService.publish(principal, kb_id, build_id)`；`ReleaseService.read_evidence(principal, kb_id, release_id, evidence_id)`。

- [ ] 审计端口及资源后建立本项目独立 PG17/pgvector 容器，绑定 127.0.0.1:55438；生成仅存本地的密码及来源根配置。
- [ ] 写真实 PG 集成测试：跨库与只读写入拒绝、路径逃逸/符号链接逃逸拒绝、固定旧证据不随重解析变化、撤回单源仍保留其他支持、未就绪发布失败、回退后版本完整。
- [ ] 运行测试确认缺实现导致失败。
- [ ] 创建通用模型迁移、独立 DB 角色与知识库隔离策略；实现内容寻址、不可变解析版本、证据多对多、不可变发布 manifest 和事务指针切换；所有读取检查当前授权。
- [ ] 运行 `uv run pytest tests/integration/test_store.py -q`，成功后记录命令和结果并提交本任务文件。

## Task 3：真实解析、模型适配与持久任务

**Files:** `src/gsm/adapters/mineru.py`、`src/gsm/adapters/llm.py`、`src/gsm/adapters/embedding.py`、`src/gsm/tasks.py`、`src/gsm/worker.py`、`tests/test_adapters.py`、`tests/integration/test_tasks.py`、`docs/setup.md`。

**Interfaces:** `Parser.parse(source_version_id) -> ParsedDocument`；`LLM.extract(schema, blocks, policy) -> ExtractionBatch`；`Embedding.embed(texts) -> list[list[float]]`；`TaskService.submit(principal, kb_id, kind, payload, idempotency_key) -> Task`；`TaskService.get(principal, kb_id, task_id)`。

- [ ] 核实 MinerU 安装调用方式、解析输出和许可；确认 deepseek-flash provider/base URL/model ID/凭据来源及结构输出，缺少时询问配置位置而非密钥内容。
- [ ] 写失败测试：解析保留页/块/表格定位，错误 JSON、超时、维数错误均明确报错；幂等同请求复用任务、异请求冲突，重启后从检查点恢复。
- [ ] 运行 `uv run pytest tests/test_adapters.py tests/integration/test_tasks.py -q` 确认失败。
- [ ] 实现有上限重试、超时和调用预算；日志脱敏；持久任务阶段与检查点，模型响应按任务 1 Schema 校验。测试替身仅用于错误注入，不充当真实 E2E。
- [ ] 同命令通过，再实际解析一份小 PDF、调用一次 LLM 和 Embedding，记录版本、耗时和输出检查；提交文件与无敏感证据。

## Task 4：候选、核验、图、索引、Wiki 与检索

**Files:** `src/gsm/build.py`、`src/gsm/review.py`、`src/gsm/graph.py`、`src/gsm/search.py`、`src/gsm/wiki.py`、`src/gsm/retrieval.py`、`tests/integration/test_build.py`、`tests/integration/test_retrieval.py`。

**Interfaces:** `BuildService.preview/start(principal, kb_id, domain_version_id, source_version_ids)`；`ReviewService.decide(principal, kb_id, candidate_ids, decision, reason)`；`QueryService.records/paths/search(principal, kb_id, release_id, query)`；`RetrievalService.retrieve(principal, kb_id, release_id, question)`。

- [ ] 写失败测试：同名身份未决、条件不同不误报冲突、无证据/推断/冲突门禁、精确单位及表格表头、关系每步可回证据、图有循环也能限界结束、索引/Wiki 失败不得切发布。
- [ ] 运行 `uv run pytest tests/integration/test_build.py tests/integration/test_retrieval.py -q` 确认失败。
- [ ] 实现候选对齐、证据定位及结构门禁；身份缺失、冲突、推断、业务歧义及领域指定项强制审核。模型建议与人工决定分开保存。
- [ ] 实现有界递归图、结构条件过滤、中文全文方案与子串基线实测、向量融合；Wiki 从记录生成并检查引用；依赖更新优先正确性，允许整库重建。
- [ ] 实现产品内有预算 Retrieval Agent，多轮调用受控工具，输出依据和未知项；记录模型计划与工具执行结果；固定会话 release_id。
- [ ] 同命令通过，补源更新、旧版持续可读、缺证据拒答的端到端检查；提交。

## Task 5：双 MCP 与外部合同验收

**Files:** `src/gsm/mcp/developer.py`、`src/gsm/mcp/consumer.py`、`src/gsm/mcp/resources.py`、`src/gsm/cli.py`、`docs/reference/mcp.md`、`tests/e2e/test_mcp.py`。

**Interfaces:** 两套 MCP 工具按设计文档映射任务 1–4 服务；开发者提供 discover_spec 和样例资源；使用者含 retrieve 与底层取证工具；CLI 提供 migrate、worker、serve-developer、serve-consumer。

- [ ] 写真实 MCP 客户端失败测试：发现规范→提交领域→预览→审核→构建→发布→第三角色检索→按引用读原文；覆盖 schema 错误、任务失败和版本不匹配。
- [ ] 写越权测试：只读直接调用写工具、伪造 kb/release/evidence/task ID、任意路径、反馈不能改事实；不能仅检查工具是否隐藏。
- [ ] 运行 `uv run pytest tests/e2e/test_mcp.py -q` 确认失败。
- [ ] 实现两端入口、固化 Schema、服务端鉴权、任务轮询与具体错误；原件、索引和派生内容统一授权。
- [ ] 同命令通过并用外部客户端重跑一次；导出工具合同及无凭据配置示例后提交。

## Task 6：引导工作区与三领域实验

**Files:** `templates/developer-workspace/AGENTS.md`、`templates/developer-workspace/START.md`、`docs/developer-guide.md`、`docs/consumer-guide.md`、`src/gsm/onboarding.py`、`src/gsm/evaluation.py`、`tests/e2e/test_onboarding.py`、`experiments/protocol.md`、`experiments/results/`。

**Interfaces:** `OnboardingService.get/save(principal, kb_id, state)` 保存目标、来源、问题、已确认项、未决项、下一步及领域版本；`EvaluationService.run(principal, kb_id, release_id, dataset_id, mode)` 返回逐题结果与汇总，mode 为 baseline 或 semantic。

- [ ] 写失败测试：从启动语发现指南，读取样本后生成候选包，业务歧义提供推荐与选项，恢复后不重复询问；无法自动确定的事项不可静默确认。
- [ ] 运行 `uv run pytest tests/e2e/test_onboarding.py -q` 确认失败；实现持久引导状态、工作区初始化及使用指南后运行通过。
- [ ] 对汽车清单复核哈希与适用性，选约 12 份代表性资料；与用户冻结 40 道人工证据基准（含至少 8 道关系组合题）、留出集和质量阈值。
- [ ] 固定产品版本与迁移，交付第二、第三窗口独立验收；不得代替第二窗口手工编写汽车资产后宣称其独立建库成功。
- [ ] 比较同模型同预算的 baseline/semantic，记录正确性、条件、证据、拒答、时间、Token、费用和构建成本，保留失败样例。
- [ ] 用户选定另两个不同领域，各建立约 20 道人工基准；在同版产品上复验。若升级产品，记录缺口并重跑既有领域。
- [ ] 运行 `uv run pytest -q` 及真实角色流程，形成明确区分自动检查、真实 E2E、人工验收与未完成项的报告；显式提交发布文档和验证记录。

## 执行与完成界限

建议本窗口顺序实施，接口紧密相依，避免每个任务另开实施上下文；必要的审阅按适用工作流执行。任务 1–5 完成只表示产品可交付独立试用，任务 6 的真实模型、独立窗口与三领域实验缺一不可，不能以自动测试通过宣称研究目标成立。
