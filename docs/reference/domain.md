# 领域定义合同 v1

这是给知识库开发者 Codex 的机器接口说明。用户从“我要开始创建知识库”进入引导，不需要手写本文件所述格式。当前实现阶段仅完成领域定义校验，不代表构建和 MCP 已可用。

## 领域包入口

`domain.yaml` 使用纯数据 YAML；用 `yaml.safe_load` 读取后调用 `gsm.domain.validate_domain(data)`。禁止 Python 标签、任意 SQL、执行插件及未知字段。完整非汽车示例见 `examples/minimal/domain.yaml`。`schema_version: '1'` 固定合同版本，所有 ID 为小写字母起始的英文数字下划线，最长 64 字符；显示名称可用中文。

顶层：`id`、`name`、`schema_version`、`types` 为必需项。可选 `description`、`aliases`、`properties`、`relations`、`events`、`rules`、`conditions`、`policies`。未定义列表默认为空。

## 定义类别

- types：`id/name/identity`，identity 引用适用于此类型的 string/enum/decimal 属性。identity 为空表示身份规则尚未给定，实际对象必须保持未决，不能靠同名合并。
- properties：`id/name/subject_types/value_type`；可声明 `units`、`enum_values`、`reference_types`、`item_type`、`required_conditions`、`require_review`。
- relations：`id/name/subject_types/object_types`，可声明 `required_conditions`、`require_review`。
- events：`id/name/roles`，每个角色有 `id/object_types/required`；一个事件内角色 ID 唯一。
- conditions：`id/value_type`，及与属性相同的值约束；条件独立定义，不因资料缺失而虚构默认值。
- rules：`id/name/applies_to/when/conclusion`，默认需审核；首版用于表示规则，后续规则求值能力单独验证，不支持任意代码。
- policies：`extraction/retrieval/source_scope/additional_review`；文本是受权限约束的业务指导，不能覆盖产品门禁或请求凭据。

同一类别内 ID 不可重复。所有类型、身份属性、事件角色、规则条件引用必须已定义。

## 值与条件

value_type 支持 string、boolean、decimal、enum、date、interval、quantity、object_ref、list。enum 必须给非空 enum_values；object_ref 必须给 reference_types；list 必须给 item_type，元素可为 string/boolean/decimal/date/quantity/object_ref。数量值用十进制字符串与单位，例如 `{"value":"123.450","unit":"CNY"}`，禁止 NaN/Infinity。此阶段校验的是领域定义；日期、区间及对象实际值将在语义记录层校验。

条件树：all/any 有非空 args，没有 field/value；叶节点有 field 且无 args。eq/ne/lt/le/gt/ge 使用单值，in 使用非空列表，between 使用两个升序边界。unknown 只有 field，没有 value，明确表达未知。field 引用已定义条件。单位转换不会由字符串相似自动推断。

## 校验与错误

`validate_domain(data: dict) -> DomainDefinition` 返回可序列化模型；失败抛出 `ProductError`，code 为 INVALID_DOMAIN，details 包含 path 和 reason，不包含原始输入。未知字段也报错，不静默丢弃。机器 Schema 位于 `docs/reference/domain.schema.json`，它检查结构；跨定义引用必须调用校验器，不能仅依赖 JSON Schema。

当前不支持领域包包含可执行代码。分离的 extraction/retrieval 文件将在包加载器中限定为包内相对路径，尚未实现前请把说明放入 policies。

## 证据门禁补充

数量单位可声明 `unit_aliases`，例如 `units: [CNY]` 与 `unit_aliases: {CNY: [元]}`。别名必须是同单位的不同写法，不能把有不同数量级的单位直接当等价别名；产品解析原文的阿拉伯数字以及“万、亿、万亿”倍率，再与数值和单位共同比较。未声明的单位解释不会自动确认。

source_statement/observation 的数值、单位和条件值必须可在引用中找到依据。检查失败会进入修正候选；用户不能直接确认绕过必要的证据检查。这些是必要的词面检查，仍不能证明主语、条件和结论之间的业务含义正确；真实领域必须经过人工证据基准及独立窗口验收。

身份键只按定义中声明的 identity 属性构造；额外身份字段会被报错，decimal 身份值规范化后比较。自动修正被替代的尝试保留审核轨迹，但不再作为有效事实制造冲突。已拒绝、已失去全部有效来源支持或其他领域定义版本中的记录不参与本次自动冲突比较。
