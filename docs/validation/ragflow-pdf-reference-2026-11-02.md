# 本地 RAGFlow PDF 实现借鉴（2026-11-02）

范围：只读检查 `/Users/jacky/code/ragflow`，提交 `12d9a38e2`。该目录是带有 Go 重构的本地版本，不将这些能力泛化为任意上游 RAGFlow 版本。没有运行其完整服务、模型或 PDF E2E，没有读取汽车原文或独立评测目录，也没有修改 RAGFlow。

## 可借鉴的机制

| 本地实现证据 | 已实现的机制 | 对本产品的建议（尚未实现） |
|---|---|---|
| `internal/entity/table.go`，TableData / TableCell | 稠密 Grid，HeaderRows、Caption、Page，RowSpan/ColSpan、Covered 和原点指针 | 建立统一文档结构层，表格不再只作为散落文字；保留原件与解析版本 |
| `internal/ingestion/component/chunker/table.go`，expandHTMLTableRows | 按数据行形成块，每块带完整表头和标题；合并单元格经 ResolveRows 投影；不伪造行级坐标 | 用“表头＋行＋单位＋范围说明”作为抽取单元，记录每行是否已处理，不以字符覆盖代替事实覆盖 |
| `internal/parser/parser/pdf_result.go`，NormalizeResult / appendPDFItem | 多解析器结果归一；表格结构和说明文本分开；无正文但有裁图区域的媒体对象保留；坐标合法性检查 | 空公式/纯图片不能被当前 from_middle 的非空文字条件直接排除；以显式未识别单元保留，报告覆盖缺口 |
| `internal/ingestion/component/vision_enhancement.go`，maybeDispatchVisionEnhancement | 按媒体区域裁图并调用视觉模型；已描述媒体避免二次调用；并发、超时和内存准入；不可用时输出 warning；结构化表格的视觉说明作为独立 note 添加 | 只对需要的区域补充识别，缓存按原件哈希、页、区域和解析/模型版本建立；说明标注模型来源，不能覆盖原始表格或自动当作已确认事实 |
| `internal/deepdoc/parser/pdf/parser.go`，processPageBoxes | 按页字符质量选择 OCR 策略；空/乱码字符进入检测识别；渲染失败等有降级路径 | 每页独立判定数字文字、扫描或混合内容；结合区域遗漏报告，不再对整份文档只设一个 txt 模式 |
| `internal/rag/prompts/vision_llm_figure_describe_prompt.md` | 区分数据图和一般图片，要求保留可见原文、枚举数据点和标签 | 对图表、流程图分别要求可核查结构输出；不能用自由描述代替数据点/箭头证据 |

## 不应直接照搬或宣称已解决的部分

- 表格按行切分以正确的上游表格识别为前提。当前合成样本中 MinerU 未输出表格结构，单接一个行切块器无法恢复缺失的行列；需要布局/表格识别或区域视觉补充。
- RAGFlow 结构化内容和 chunk 不等于本产品的 object/assertion/relation/event/rule。模型将全局公式错误归属某设备的问题仍需主体—属性证据校验。
- 不能据本次代码阅读声称其公式 LaTeX、变量绑定、数学求值或全部跨页表格已经可靠。相关路径依赖后端、配置和模型，必须用同一合成样本单独验收。
- 代码中 table 页号定义为 0-based；有些其他位置由 producer 归一。我们的文档块页码是 1-based，不能复制数字而不转换，也不能给表格每行伪造精确区域。
- 多后端服务、整个 Go/DeepDoc 栈不是本产品当前必须引入的依赖。先规范通用信息单元和能力契约，再验证现有本地 MinerU、补充文本提取和区域视觉工具的组合。
- 新增模型描述需要区分 original_text、OCR、vision_description、结构恢复和推断；视觉结果有证据位置不等于语义正确，用户确认与机器校验要分开。

## 建议落地顺序

1. 通用文档单元与逐页覆盖报告，保留缺失/失败区域、来源、坐标及解析版本。
2. 表格结构恢复与带表头的行级提取，保留标题、脚注、条件的归属；通过遗漏行的合成回归。
3. 按需 OCR/视觉增强，先处理图片页和空公式区域，设置预算、缓存、失败状态和重试边界。
4. 提取覆盖检查和主体归属校验；Wiki 与问答保留未解决范围，不能用“模型全部复核通过”掩盖遗漏。
5. 同一批独立通用样本比较信息保真、语义完整性、错误归属、Token 和分段耗时。通用回归过后第二窗口重建汽车知识库，第三窗口独立评测；第一窗口只读取允许的结果。

本次产出为参考分析，没有修改产品解析逻辑、固定 Schema 或领域数据。
