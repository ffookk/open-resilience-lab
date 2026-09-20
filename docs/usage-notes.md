# 使用细节

- JSON 字段名区分大小写，例如 `title` 不能写为 `Title`。
- `schema_version` 必须写作整数 `1`；字符串 `"1"` 和布尔值 `true` 都不接受。
- 可选文本 `notes` 和 `household[].needs` 不填写时应省略字段；写成空字符串或 `null` 会校验失败。
- 可选列表 `household` 和 `sources` 可以省略或写成 `[]`；不能写成 `null`。
- 家庭成员已填写 `name` 但省略 `needs` 时，HTML 会显示“未填写 / Not provided”。
- 文本首尾空白不会自动删除；仅由空白组成的文本会被拒绝。
- 字段长度按 Python 字符串字符数计算，整个文件的 256 KiB 限制按 UTF-8 字节数计算。
- 普通文本可包含换行与制表符；在 JSON 字符串中须写成 `\n`、`\t` 等合法转义。
