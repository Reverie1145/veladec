# 让 AI 自己安装 skill 的提示词

贴给有 shell 的 AI 助手（Claude Code / Codex / Cursor）。它会装好 veladec，并把 `vela-reverse` skill 落进助手的技能目录，之后遇到 `.rpk` 自动走这套流程。

---

帮我安装 `vela-reverse` skill，让以后遇到快应用 `.rpk` / `.jsc` 你能直接反向分析。按顺序做，每步给出实际命令与结果：

1. **装工具**。二选一：
   - 仓库已在本地：`cd <veladec 仓库路径> && python3 -m zipapp . -o /tmp/veladec.pyz -p '/usr/bin/env python3'`（若仓库根已有 `veladec.pyz` 就跳过）
   - 从 GitHub 取：`curl -L -o /tmp/veladec.pyz https://github.com/Reverie1145/veladec/releases/latest/download/veladec.pyz`
   然后 `install -Dm755 /tmp/veladec.pyz ~/.local/bin/veladec`，确认 `~/.local/bin` 在 `PATH`，跑 `veladec --version`。
2. **验工具**。用任意 `.rpk` 跑 `veladec info TARGET` 与 `veladec selftest TARGET`，必须看到 `selftest: OK`。没有样本就跳过这一步，但要在报告里写明"未见真实样本"。
3. **落 skill**。创建目录 `~/.claude/skills/vela-reverse/`（Codex 用 `~/.codex/skills/vela-reverse/`，其他助手用其 skills 根目录），把仓库里的 `skills/vela-reverse/SKILL.md` 复制进去；若本机没有该文件，用 `curl -L -o ~/.claude/skills/vela-reverse/SKILL.md https://raw.githubusercontent.com/Reverie1145/veladec/main/skills/vela-reverse/SKILL.md`。
4. **自检 skill**。`head -3 ~/.claude/skills/vela-reverse/SKILL.md` 必须看到 YAML frontmatter 的 `name: vela-reverse`；`wc -l` 报告行数；把文件里出现过的命令抽三条干跑（例如 `veladec mv TARGET --file pages/index`），确认命令存在（`veladec <cmd> -h` 不报未知子命令）。
5. **报告**。输出一张表：工具路径 / 版本 / selftest 结果 / skill 路径 / skill 行数 / 三条命令的 `-h` 是否通过。任何一步没成功就如实写"失败 + 原始报错"，不要跳过。

装完之后的用法：直接把 `.rpk` 路径和问题丢给我，我会按 `vela-reverse` 的流程走——`info` → `mv` 定位 → `decompile`/`disasm` 读 → `run` 跑 → 独立复算对账 → 交付带偏移证据的结论。

---

## 附带：如果你只想手动装

```sh
# 1) 工具
install -Dm755 /path/to/veladec.pyz ~/.local/bin/veladec
veladec --version

# 2) skill
mkdir -p ~/.claude/skills/vela-reverse
cp /path/to/veladec/skills/vela-reverse/SKILL.md ~/.claude/skills/vela-reverse/

# 3) 验
veladec selftest TARGET | tail -1
head -3 ~/.claude/skills/vela-reverse/SKILL.md
```
