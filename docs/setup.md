# 本地开发环境（实现中）

Python 3.12，使用 uv.lock 固定当前 macOS 环境依赖。`uv sync --frozen` 安装；本机遇到 uv 网络读取超时可用 pip/curl 下载 wheel 至忽略的 runtime/wheels，再以 `uv sync --no-index --find-links runtime/wheels` 安装。wheel 不提交。

复制 `.env.example` 至 `.env`，分别生成三个独立数据库密码；本机 `.env` 权限应为 0600。启动 `docker compose up -d --wait`，默认仅绑定 127.0.0.1:55438，不复用既有 PG。不要删除已有容器或数据卷。

迁移入口目前为 `Store(Settings.load()).migrate()`，任务表由 `TaskService(store).migrate()` 初始化。自动化测试依赖本项目 PG；执行 `uv run --frozen --no-sync pytest -q`。

原件导入仅允许经签名角色配置指定的文档收件目录内的相对文件，存储到 `GSM_FILE_ROOT/<kb_id>/<sha256>`，源版本独立于路径。工作目录暂为项目根；发布 CLI 会固定路径解析。

## 模型

本机凭据来源为用户指定的 `~/code/.env`，只读取 DEEPSEEK_API_KEY，绝不 shell source 整个文件。默认 https://api.deepseek.com、deepseek-flash；用 JSON Output（非 strict JSON Schema），返回仍须产品校验。官方文档：

- https://api-docs.deepseek.com/quick_start/agent_integrations/
- https://api-docs.deepseek.com/guides/json_mode/

Embedding 为 http://127.0.0.1:8010/v1，模型 qwen3-embedding-0.6b-mlx，1024 维；实际输出检查维度和有限数值。

## 解析

使用 MinerU 本地 `mineru-kit parse <file> --tier flash --ocr-mode txt --disable-image-analysis --format middle_json -o <output>`，不使用 --remote，不静默上传。保留 middle JSON、页块位置、表格结构。flash 是首条数字 PDF 链路；扫描件需要 OCR 后端，必须另行验证，不能把无正文当成功。

当前本地源码位于 ../MinerU；其许可为 Apache 2.0 加附加商业阈值及在线服务署名条款，参见该版本 LICENSE.md。本项目通过进程边界调用，不复制其实现；后续分发必须重新核对实际版本及模型权重许可。

仅纯文本/Markdown采用明确标记的 plain-text-v1，不把它当 MinerU PDF/OCR 验证。

## 角色工作区

配置 GSM_CREDENTIAL_SIGNING_KEY 为独立随机值，保留在 .env；角色与知识库作用域经签名验证，修改角色字段会被拒绝。更换签名密钥会使已有角色配置失效，需由产品管理员重新签发。

```bash
uv run --frozen python -m gsm.cli migrate
uv run --frozen python -m gsm.cli init-workspaces --root ../gsm-knowledge-workspaces
uv run --frozen python -m gsm.cli worker --credentials ../gsm-knowledge-workspaces/developer/credentials.json
```

init-workspaces 拒绝覆盖非空目录，也拒绝产品目录内的目标（含符号链接）。第二、第三窗口分别打开 ../gsm-knowledge-workspaces/developer 和 consumer。知识库工作目录与产品软件目录分离，资料和领域资产不提交产品 Git。第二窗口说“我要开始创建知识库”；第三窗口等待开发者提供发布版。工作区含项目级 MCP 配置，不修改用户全局 Codex 配置。客户端可能要求用户信任新工作区；这是客户端设置，不代表产品批准写入。

复现本地 MinerU flash 运行环境（源码只读，不在源码目录安装或修改）：

```bash
uv run --frozen python scripts/setup_mineru.py --source ../MinerU
```

当前安装为 macOS、固定 MinerU commit、原生数字正文路径；requirements-mineru-flash.lock 固定依赖。可用 --wheelhouse runtime/wheels 从本地 wheel 安装。扫描件 OCR 尚未覆盖。

实时合成资料链路烟测：`uv run --frozen python scripts/smoke_mcp.py`，需要本地 Embedding 和 DeepSeek 服务可用，会产生真实模型调用与实验知识库。它不替代独立窗口和真实领域验收。

本机检查发现尚未信任工作区时，`codex mcp list` 不会加载项目配置。可改用下列启动器，它只为新会话显式传入对应 MCP，不修改全局设置：

```bash
python3 ../gsm-knowledge-workspaces/developer/start-codex.py
python3 ../gsm-knowledge-workspaces/consumer/start-codex.py
```

CLI 会话启动后，开发者输入“我要开始创建知识库”。图形界面方式仍需按客户端提示信任对应工作区，再检查 MCP 连接。已通过独立原生 Codex CLI 的引导、汽车建库和消费预验收，见 docs/testing/three-codex-results.md；图形客户端体验仍待用户实际确认。

新工作区不预选任何外部资料目录。developer/documents 是空的产品收件目录，不代表用户已有资料位置。建库时先由用户提供文件或目录，Codex 将选定样本复制到收件目录，再调用 register_source。不要递归扫描其他项目猜测用户知识来源。

正式试用应使用产品 Git 仓库之外的独立目录，例如 `../gsm-knowledge-workspaces`。初始化生成空收件目录和新的知识库作用域，不预置资料位置。启动器显式传入 workspace-write 并清空额外 writable_roots，不改全局设置。该写沙箱不是读取隔离；本次验收额外使用了外层 OS 读取限制，见测试规范。[OpenAI 官方沙箱说明](https://learn.chatgpt.com/docs/sandboxing)。

计时诊断默认关闭。需要按阶段复现时，为 MCP 服务和 worker 设置 `GSM_TIMING_LOG=/absolute/path/timings.jsonl`；可选 `GSM_TIMING_ROLE=developer|consumer|worker` 标记来源。日志记录阶段、起止时间、耗时和作用域 ID，不记录凭据、提示词、原文或异常正文。嵌套阶段不可与父阶段重复求和；网络失败且未返回 usage 的上游调用不能据此准确计费。


## 检索预算与可选分词器

检索默认最多 8 轮、累计 64000 token。语义词汇和来源名称来自当前发布版；产品不会预置领域知识。回答为 supported 前还要基于实际已读原文做一次模型一致性复核。这是模型检查，不能代替专家金标准。预算不足以完成回答和复核时，返回不足，不跳过复核。

未配置分词器时按 UTF-8 字节上界估算输入，中文和重复长原文可能使这个估算过于保守。可安装与服务模型匹配的官方分词器。本次实验的 deepseek-flash 对应 DeepSeek-V4.1-Flash；远端别名可能变化，使用前应重新核对，不能默认未来仍相同。分词器只用于本地输入估算，带 15% 余量和 256 token 开销；服务端 usage 是实际用量依据，超出估算会报 TOKEN_COUNT_MISMATCH。

本次文件来自官方仓库固定版本（不提交模型文件）：

```bash
mkdir -p runtime/tokenizers/deepseek-v41
curl -fL --retry 3 \
  https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/resolve/314113f8a7dadb388215396ba5fbee2c610a04d6/tokenizer.json \
  -o runtime/tokenizers/deepseek-v41/tokenizer.json
shasum -a 256 runtime/tokenizers/deepseek-v41/tokenizer.json
```

预期 SHA-256 为 `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b`，6367257 字节。核对后在本地 `.env` 配置 `.env.example` 中两项 GSM_TOKENIZER 参数并重启服务。不要给不匹配的服务模型配置此文件。模型控制符不会把不可信资料中的同名文本当作单个控制 token。

依据：[官方 token 用量说明](https://api-docs.deepseek.com/quick_start/token_usage/)、[模型信息](https://api-docs.deepseek.com/quick_start/pricing/)、[官方分词器使用说明](https://github.com/deepseek-ai/deepseek-recipe/blob/main/docs/tokenizer.md)。


## 产品、知识库与汽车验证目录

产品目录只保存通用代码、依赖和产品文档。每个知识库使用独立外部工作目录；初始化拒绝把开发者/使用者工作区放到产品内部。默认原件存储为 `~/.local/share/general-semantic-model/files/<kb_id>`，本机通过 `GSM_FILE_ROOT` 配为 `/Users/jacky/code/gsm-runtime-data/files`；不要把模型依赖目录和知识库原件仓库混在一起。未配置来源时没有默认收件目录，具体资料由用户提供。

本机汽车独立验证目录为 `/Users/jacky/code/gsm-automotive-validation-20261102`：

```text
general-semantic-model/                 # 第一窗口：产品开发
../gsm-automotive-validation-20261102/
    developer/                          # 第二窗口：文档、领域包、建库结果
    consumer/                           # 第三窗口：只读问答、测试与反馈
    control/                            # 第一窗口私有：基准、服务、证据、计时
    artifacts/                          # 复现归档，不进入产品Git
../gsm-runtime-data/files/<kb_id>/       # 外部原件存储，按KB隔离
```

汽车测试分别运行：

```bash
python3 /Users/jacky/code/gsm-automotive-validation-20261102/developer/start-codex.py
python3 /Users/jacky/code/gsm-automotive-validation-20261102/consumer/start-codex.py
```

这些汽车启动器使用独立 Codex 会话状态、签名KB作用域、分别鉴权的HTTP MCP和外层 macOS OS 沙箱。产品、私有基准及另一角色目录不可读写；本角色工作区可写。第三窗口API不提供建库和发布写能力。原生内部沙箱仅在该外层OS沙箱确已启用时关闭，不能单独复制关闭内部沙箱的参数运行。两个原生Codex会话均实测产品写入返回PermissionError，而本角色工作区写入及公开MCP读取成功；另有22项协议/OS边界检查通过。

这个额外OS隔离是汽车验证入口配置；普通init-workspaces启动器仍是workspace-write，不要把直接打开文件夹等同于OS隔离，也不要把实验配置当作已交付的生产多租户安全。依据：[OpenAI官方权限与沙箱说明](https://learn.chatgpt.com/docs/agent-approvals-security)。

此前 `/Users/jacky/code/gsm-knowledge-workspaces-20261102` 保留给用户空白试用，未预置汽车文档。历史实验材料已从产品runtime搬到上述汽车目录的control归档，不改写历史日志中的原路径。归档脚本输出也改到实验目录；烟测在系统临时目录生成资料，不再写产品的知识库目录或自动改写已提交测试报告。

## 共用目录初始化（新流程，尚未完整验收）

```bash
uv run --frozen python -m gsm.cli init-kb --root ../automotive-kb --name 汽车知识库
```

该命令由产品执行，不调用Codex或LLM：迁移通用数据库结构、登记空知识库、创建documents/domain/wiki/releases/reports空目录。未导入任何汽车知识。两角色都以automotive-kb为根目录，分别使用start-producer.py与start-consumer.py；producer是业务角色名，内部历史开发者API身份暂保留developer以兼容合同。

此入口目前完成初始化和共用目录骨架。共用目录下的凭据隔离、完整Pipeline与发布产物导出尚未完成，不应替代已验证OS隔离的旧汽车测试入口开展正式验收。未自动迁移或覆盖旧知识库。
