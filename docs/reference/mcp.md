# MCP 合同 v0.1

开发者和使用者分别启动 stdio MCP，服务端固定经签名身份和知识库作用域，客户端不能通过工具参数切换角色。工具完整输入输出 Schema 以本目录 `mcp.developer.json`、`mcp.consumer.json` 为准，由实际服务器导出。

公共错误 envelope 为 `{"error":{"code":...,"message":...,"details":...,"retryable":...}}`。任务成功提交不表示任务完成；轮询 get_task 查看 status、stage、checkpoint 和 error。只有 succeeded 才能使用结果。任务对象的 error=null 是正常值，不是错误 envelope。

长任务由独立 worker 执行。相同 kind、知识库和幂等键复用任务，输入不同则冲突。失败且 retryable 时可 retry_task；恢复复用任务 ID 和检查点。worker 使用逐任务数据库锁避免多进程并行重复执行。

所有消费接口显式绑定 kb_id/release_id，证据不能跨版本跳转。developer 的 read_candidate_evidence 可查看尚未发布候选原文；consumer 只能读取发布版。消费者 feedback 只写反馈队列。领域定义及候选不能包含任意 SQL/Python。

本机 stdio 隔离指服务工具与数据库角色隔离，不是对拥有同一 macOS 用户文件权限的进程提供操作系统沙箱。不要给第三窗口产品管理员配置或让它读取产品私有文件。

Codex 项目级 `.codex/config.toml` 和 stdio cwd 的配置依据：[官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。客户端要求项目可信后才加载项目级配置；本项目不更改全局信任设置。
