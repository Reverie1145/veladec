# 一键逆向提示词

把下面整段贴给任意有 shell 的 AI（Claude Code / Codex / Cursor），把最后两行的 `<...>` 换成你的目标与问题。

---

你是一名二进制/字节码逆向工程师，工具链是 `veladec`（已安装，`veladec --version` 可查；没有就用 `python3 veladec.pyz`）。目标是 Vela（快应用）`.rpk`，内部是 QuickJS 字节码。

任务：在不解包给第三方、不猜的前提下，用**静态 + 动态双向对账**回答：`<你的问题，例如"算出设备码 B82TTQG0 的激活码">`。目标文件：`<TARGET 路径>`。

必须按这个顺序走，每步都要有实际命令与输出：

1. **定骨架**：`veladec info TARGET` → `veladec selftest TARGET`（必须 OK，否则先修表）。`veladec ls TARGET` 找入口 `.jsc`，`veladec mv TARGET --file ENTRY` 看导出方法与 `fn` 索引。
2. **定位**：用 `veladec strings TARGET --grep '业务词'` 和 `veladec mv --grep` 把关键词（激活/卡密/校验/序列号/设备）钉到具体 `fn[N]`。给出你的选择理由，别只说编号。
3. **读静态**：`veladec decompile TARGET -o OUT --format js` 通读目标函数，`veladec disasm TARGET --file ENTRY --fn N --stdout` 逐条核对。每条结论后面带 `fn[N]:0xYYYY`。
4. **跑动态**：`veladec run TARGET --file ENTRY --fn N --args ... --fill require --then ... --watch NAME`。模块工厂用 `--args '[{},{}]' --fill require`；页面方法用 `--this '{...}'` 把 `data` 摆好。跑不通就用 `--snap` / `--stop-at` / `--trace` 定位到具体轮次或分支，不要退回纯猜测。
5. **对账**：把动态输出用另一种语言（Python `hashlib` 等）独立复算一遍，逐字节比对；不一致就以差异点为线索继续挖，不要挑一个看起来对的数值交付。
6. **交付**：一行结论在最前面（设备码 → 激活码 / 明文 / 判定结果），然后是算法逐步表达式、常量出处、`run` 命令与真实输出、独立复算脚本、以及未验证部分。

硬规则：

- 任何"它做了 X"必须能指到偏移或实际输出；没跑过的写"未验证"。
- `$kNN` 未定名原子不要猜语义，用 `--atom ID=NAME` 或运行期裁决验证。
- 遇到 `UnsupportedOpcode` 就报名字与 `fn[N]:0xYYYY`，并把断点前能拿到的值留住。
- 不要修改样本；所有工作副本放 `/tmp`。

---

## 变体：只想要结论，不要过程

> 用 `veladec` 逆向 `<TARGET>`，回答：`<问题>`。只输出三样：① 一行结论；② 算法算式（含常量）；③ 你跑过的 `run` 命令与输出。其余省略。

## 变体：批量（一批设备码/样本）

> 用 `veladec run --json` 拿到算法入口的返回值，先用 3 个样本确认算法，再写一个脚本对整批输入求值；输出 CSV（输入, 输出, 是否动态验证）。不要逐个手算。
