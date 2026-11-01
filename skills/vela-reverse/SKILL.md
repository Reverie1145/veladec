---
name: vela-reverse
description: Reverse-engineer Vela (快应用 / quick-app) .rpk packages with veladec — decompile, disassemble, map modules, and run bytecode dynamically to recover algorithms, license checks and protocol logic. Use when a target is a .rpk/.bin quick-app, a pages/*.jsc bundle, or when the task names 快应用 / Vela / veladec / rpk.
---

# Vela 逆向（veladec）

一个 `.rpk` 就是 zip + 若干 `.jsc`（QuickJS 字节码，Vela fork）。**读字节码**用 `decompile`/`disasm`，**找该读哪个函数**用 `mv`，**验证到底算出什么**用 `run`。三条命令分工，别混着用。

## 0. 先确认工具在

```sh
veladec --version            # 或 python3 veladec.pyz --version
veladec info TARGET          # 指纹 / 文件数 / 函数数 / 自动选表依据
veladec selftest TARGET      # 必须 selftest: OK，badatom/badjump 非 0 就先解决解码
```

`info` 报的 `penalty` 越小，opcode 表越可信；`selftest` 的 `not_exact`/`badjump` 非 0 说明这张表不对，换 `--table` 或补表，别硬读。

## 1. 定骨架（不看代码也能答的三个问题）

```sh
veladec unpack TARGET -o OUT            # 解包
veladec ls TARGET                       # 有哪些 .jsc，入口是哪个
veladec mv TARGET --file pages/index    # 入口导出什么、页面对象在哪、fn 索引
veladec mv TARGET --file pages/index --grep lic --names 40   # 名字索引：谁读写 lic
```

`mv` 输出里先看 **exports / 方法表**，再看 **closure 绑定**（`vN <- fn[X].rM` 说明闭包变量真实来源）。找不到入口就把 `--grep` 换成业务词（`lic`、`code`、`activate`、`verify`、`serial`、`device`）。

## 2. 读算法（静态）

```sh
veladec decompile TARGET -o OUT --format js     # 伪 JS，先通读
veladec disasm TARGET --file pages/index --fn 23 --stdout   # 关键函数逐条看
veladec strings TARGET --grep '激活|卡密|密钥|错误|invalid'  # 提示语定位分支
```

规矩：

- **伪 JS 是给人看的，结论必须回到 asm 的偏移**。任何"它做了 X"都要能给 `fn[N]:0xYYYY`。
- `$kNN` 是未定名的内建 atom。别猜，用 `run --atom` 或运行期裁决（见 §4）。
- 长函数先切段：跳转标签 `L00xx` 就是段边界；把 `if_false` 的目标标出来即得分支骨架。
- 循环边界看 `lt/le` + `post_inc`；`get_length`/`push_8 64` 这类常量往往是块长、轮数、表长。

## 3. 找常量（表、盐、密钥）

```sh
veladec disasm TARGET --file pages/index --fn 80 --stdout | sed -n '/push_i32/,+2p'
veladec run TARGET --file pages/index --fn 80 --args '[{},{}]' --fill require --stop-at 230 --dump
```

对象/数组字面量在字节码里是 `push_* … array_from n:N` 或 `object … define_field`；`--dump` 直接把构造完的局部变量打出来，比数 64 个 `push_i32` 快。

## 4. 跑起来（动态，最高优先级）

**能跑就别猜。** `run` 是解释器，不是模拟器：它执行真实字节码，平台 API 用桩。

```sh
# 4.1 纯函数：直接调
veladec run TARGET --file pages/index --fn 80 --args '[{},{}]' --fill require --then '7:["abc"]'

# 4.2 页面钩子：入口 + --then，看关键变量
veladec run TARGET --file pages/index --fn 80 --args '[{},{}]' --fill require \
        --device-id DEVICE_CODE --then 21 --watch devCode --watch expected

# 4.3 页面方法：--this 摆好 data，守卫条件一起给
veladec run TARGET --file pages/lock --fn 32 \
        --this '{"serial":"600192","z":"zyxw1","g":"z","h":"y","i":"x","j":"w"}'

# 4.4 定位到轮次/分支内部
veladec run ... --snap 7@2d6:5 --trace        # 第 5 次经过 fn[7]:0x02d6 时快照局部变量
veladec run ... --stop-at 22e --dump          # 断在那里，dump 全部局部
```

参数速查：

| 参数 | 用途 |
|---|---|
| `--args JSON` / `--this JSON` | 入口参数 / `this`（`--null-this` 传 null） |
| `--fill undefined\|require\|noop` | 缺省参数补什么；模块工厂 `(module,exports,require)` 用 `require` |
| `--then FN[:ARGS]` | 入口跑完后调它创建的闭包函数，可重复；页面方法自动带 `this` |
| `--storage K=V` / `--device-id` / `--now` / `--seed` | 平台环境（storage、deviceId、时间、随机数） |
| `--watch NAME` / `--watch-call FN` | 盯局部变量写入 / 盯函数调用 |
| `--snap FN@HEX[:N]` / `--stop-at HEX[:N]` | 快照不中断 / 断点（都支持第 N 次命中、`FN@` 限函数） |
| `--atom ID=NAME` | 钉死内建 atom（不同 Vela 构建会整体移位） |
| `--json` | 结果、watch、host 调用全量 JSON，便于脚本对账 |

失败处置：

| 现象 | 处理 |
|---|---|
| `UnsupportedOpcode(name…)` | 该指令解释器没实现，报给 veladec 维护者；先用 `--stop-at` 停在它前面把能拿的值拿到 |
| `fn[N] was not created by the entry call` | 该闭包由更内层的调用创建；先用 `--then` 调到创建它的那层 |
| 结果 `undefined` / `NaN` | 输入是桩值（`VELADEC-DEVICE-0001`）或 atom 裁决错，`--device-id` / `--atom` 纠正 |
| 平台回调没触发 | 漏了 `--fill require`，或模块名不在 `@app-module/system.*` 白名单 |

## 5. 对账（不给没验证的答案）

```sh
python3 - <<'PY'
import hashlib
print(hashlib.sha256(b'FS-DEV:...').hexdigest())   # 独立复算
PY
```

- 算法类结论：**用另一种语言独立复算一遍**，与 `run` 的输出逐字节比。
- 激活码类结论：给出设备码 → 激活码的完整算式 + 中间值（摘要 hex、取模余数），再给一个脚本能复现。
- 只写你亲手跑过的东西。没跑就写"未验证"，不要写"应该"。

## 6. 交付格式

```
结论：DEVICE_CODE → LICENSE（一行，最前面）
算法：fn[N] 的逐步表达式 + 每个常量出自哪个偏移
证据：run 命令 + 实际输出（含 watch/dump 关键行）
复算：独立脚本 + 结果
限制：未覆盖的路径、假设的桩值
```
