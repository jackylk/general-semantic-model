# PDF 信息提取与语义表充分性检查（2026-11-02）

结论：当前配置尚不足以支持完整 PDF 知识构建。可读段落里的简单事实有效，但无边框表格行列关联、图片页、公式符号及断言归属存在实际缺口。记录数、结构通过率、模型复核通过率均不能代替信息完整性。

## 边界与复现

本次第一窗口仅使用自己生成的 3 页通用合成 PDF，没有读取汽车原始文档、汽车评测目录或其他窗口的原始日志。测试材料和运行证据在 `/Users/jacky/code/gsm-iteration-control/pdf-information-audit/`，与产品目录及汽车知识库隔离。

- `generate.py`：生成文字、无边框表格、纯图片页、公式及上下标/希腊符号；`fixture.pdf` 为最终输入。最终第一页、第二页和第三页分别有数字文字、图片内容和符号；第一页和第三页已渲染检查，第二页的正文仅存在于嵌入图片。
- `PdfProbe.java`：使用 Lakeon 同版本 PDFBox 3.0.3，复现当前 `extractPdf` 的逐页 PDFTextStripper 操作；`pdfbox.txt` 为输出。这不是 Lakeon 全服务 E2E，没有执行 CommonMark 后续切分、embedding 或索引服务。
- `run.py`：调用当前产品初始化、原件登记、真实 MinerU、DeepSeek 提取和数据库落表。首次温度声明为 decimal，模型输出 quantity 导致一条 INVALID_VALUE；这是领域定义/模型输出类型不一致，不归因为 PDF 丢失。
- `compare.py`：将温度声明为带 C 单位的 quantity，对两路正文使用同一领域和同一真实 DeepSeek 模型提取，再执行与 pipeline 相同的 support-review 请求并构建。显式关闭 embedding，不发布，不宣称检索问答验收。PDFBox 输出在合成库中登记为派生来源，不冒充产品的原生 PDFBox 支持。
- `blocks.json`、`middle-final.json`、`semantic-result.json`、`comparison.json`：原始结构、可见块、候选、模型复核和耗时。初次 `middle.json` 来自符号字体修正前的试跑，以 `middle-final.json` 为最终符号结论依据。

代码基线：本产品 `e478c98`，Lakeon `d3adfbaa3`。合成库 ID `f767f03c-b7a1-421c-987a-9dfdc49860e7`。

复现环境使用本仓库 `.venv/bin/python` 和 `runtime/mineru/bin/python`；从产品根目录运行外部 `generate.py`、PDFBox probe、`run.py`、`compare.py`。`run.py` 只接受空的 `kb` 工作区，复测应复制脚本和输入到新的实验目录，不能删除已有数据库或覆盖证据。

## 当前两条路径

| 环节 | Lakeon 当前代码 | 本产品当前代码 |
|---|---|---|
| PDF 解析 | PDFBox 3.0.3 PDFTextStripper，逐页纯文字 | 本地 MinerU，flash / ocr-mode txt / disable-image-analysis |
| 结构及定位 | 添加 Page 标题，CommonMark 切分，映射页范围 | 原始 middle JSON、页/块/bbox/上游字段，非空文字块入 source_blocks |
| 图片/OCR | 无文本 PDF 明确拒绝，未接入 OCR | 本配置未启用图片分析；混合 PDF 可以整体成功但漏掉图片页正文 |
| 表格 | PDF 路径无专用表格结构恢复 | 本样本无边框表格退化成多个文字块 |
| 语义产物 | 该 PDF stage 输出 canonical sections，不能等同于本产品领域语义表 | 领域驱动 object/assertion/relation/event/rule、证据门禁、模型复核、Wiki/图/索引 |

Lakeon 的 MinerU 迁移方向不等于当前已实现行为。本次比较以源码和实际 PDFBox 输出为准。

## 逐项检查结果

| 已知输入 | 当前 MinerU 路径 | PDFBox 页文字 + 同一产品语义提取 |
|---|---|---|
| 设备 A/B 身份、连接方向 | 2 对象、1 有向关系正确保留 | 相同 |
| 段落明确的 20 C → 10.25 W | 正确保留 quantity 和温度条件 | 相同 |
| 表格 30 C → 12.50 W | 数字仍在文字块中，但行列关系丢失，最终没有该断言 | 行文本仍成对，但最终同样没有该断言 |
| 表格仅适用干燥环境、不是最大值 | 形成一条表格范围说明；未形成完整的表格行结构 | 相同 |
| 纯图片页的设备 C、7.75 W、流向箭头 | 未进入可检索正文、无对应语义记录 | 无文字、无对应语义记录 |
| 文本公式 P = U * I、变量单位 | 作为 string 保存，没有公式 AST/求值语义 | 相同 |
| U <= 24 V、+/- 0.5 W | 作为 string 保存，没有可执行比较/误差模型 | 相同 |
| α β γ ≤ ≥ ± | 上游识别为 equation 但 content 为空，适配器没有生成可检索块 | 字符保留在页文字中；本次领域未定义符号属性，不要求生成相应记录 |
| H 下标2 O、x 上标2 | 正文扁平化为 H2O x2；locator.content 保留 subscript/superscript 样式，但没有形成数学结构 | H2O、x 换行 2，无专用上下标结构 |
| 公式/限制/误差的主体归属 | 原文没有明确归属到设备 A，模型却将三项挂到 A；模型复核仍批准 | 同样发生 |

注意：20 C 的表格行在正文重复出现，正确提取正文那条事实不能作为表格行恢复成功的证据。上述检查是合成资料的人工逐项核对，不是汽车 benchmark 得分，也不是具有统计意义的通用准确率。

## 规模、耗时和调用

最终 MinerU 可检索块 8 个，涉及第 1、3 页；第 2 页没有正文块。

| 对比路径 | 候选 | 结构通过 | 模型复核通过 | 最终构建记录 | 提取秒 | 复核秒 |
|---|---:|---:|---:|---:|---:|---:|
| 当前 MinerU | 8 | 8 | 8 | 8 | 3.665 | 3.840 |
| PDFBox 页文字 | 8 | 8 | 8 | 8 | 7.637 | 3.997 |

两路记录构成都为 2 对象 + 5 断言 + 1 关系。每路具有 1 条关系边；公式等仅是断言 string。构建 ID：MinerU `2e870d89-2efb-40d0-bbd1-a76864afed23`；PDFBox `223e5ded-402c-490d-826b-fa3ba668053b`。

产品首次原件解析并落库耗时 1.000 秒；首次类型诊断提取 7.574 秒、6502 tokens。PDFBox probe 1.444 秒包含 Java 源码编译/JVM 启动，不能据此比较解析器性能。两路对比均为一次样本运行，模型耗时也不能作为性能结论。逐调用 usage 保留于 comparison.json。

回归检查：`pytest -q tests/test_adapters.py tests/test_source_context.py tests/test_grounding.py tests/test_sampling.py`，23 passed。现有测试通过仍未覆盖本次发现的充分性缺口。

## 后续通用改进优先级（本次未实现）

1. 解析覆盖率：逐页统计文本、图片、表格、公式与空内容；有内容却未提取的区域必须显式报缺口，不能只报整体解析成功。
2. 表格结构：保留单元格、行列、表头、标题和脚注归属，提供可引用的结构化单元格证据。仅扩大文本上下文不保证完整提取。
3. 公式/符号：保留原文区域、表达式和上下标；区分公式文字、变量定义、单位和可执行计算，缺失时保持未知。
4. 主体归属：要求断言的证据组合支持主体与属性之间的归属，不以“quote 存在”代替语义支持；模型自查不能作为唯一正确性依据。
5. 事实覆盖：按来源信息单元检查未提取行/区域；处理完全部文字、生成若干 Wiki 或模型复核全过都不等于完整建库。

本次只新增验证报告和外部实验数据，没有修改产品解析器、固定 Schema 或 Lakeon 文件。
