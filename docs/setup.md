# 本地开发环境（实现中）

Python 3.12，使用 uv.lock 固定当前 macOS 环境依赖。`uv sync --frozen` 安装；本机遇到 uv 网络读取超时可用 pip/curl 下载 wheel 至忽略的 runtime/wheels，再以 `uv sync --no-index --find-links runtime/wheels` 安装。wheel 不提交。

复制 `.env.example` 至 `.env`，分别生成三个独立数据库密码；本机 `.env` 权限应为 0600。启动 `docker compose up -d --wait`，默认仅绑定 127.0.0.1:55438，不复用既有 PG。不要删除已有容器或数据卷。

迁移入口目前为 `Store(Settings.load()).migrate()`，任务表由 `TaskService(store).migrate()` 初始化。自动化测试依赖本项目 PG；执行 `uv run --frozen --no-sync pytest -q`。

原件导入仅允许 `GSM_SOURCE_ROOT` 内相对文件，存储到 `GSM_FILE_ROOT/<kb_id>/<sha256>`，源版本独立于路径。工作目录暂为项目根；发布 CLI 会固定路径解析。

## 模型

本机凭据来源为用户指定的 `~/code/.env`，只读取 DEEPSEEK_API_KEY，绝不 shell source 整个文件。默认 https://api.deepseek.com、deepseek-flash；用 JSON Output（非 strict JSON Schema），返回仍须产品校验。官方文档：

- https://api-docs.deepseek.com/quick_start/agent_integrations/
- https://api-docs.deepseek.com/guides/json_mode/

Embedding 为 http://127.0.0.1:8010/v1，模型 qwen3-embedding-0.6b-mlx，1024 维；实际输出检查维度和有限数值。

## 解析

使用 MinerU 本地 `mineru-kit parse <file> --tier flash --disable-image-analysis --format middle_json -o <output>`，不使用 --remote，不静默上传。保留 middle JSON、页块位置、表格结构。flash 是首条数字 PDF 链路；扫描件需要 OCR 后端，必须另行验证，不能把无正文当成功。

当前本地源码位于 ../MinerU；其许可为 Apache 2.0 加附加商业阈值及在线服务署名条款，参见该版本 LICENSE.md。本项目通过进程边界调用，不复制其实现；后续分发必须重新核对实际版本及模型权重许可。

仅纯文本/Markdown采用明确标记的 plain-text-v1，不把它当 MinerU PDF/OCR 验证。
