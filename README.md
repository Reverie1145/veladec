# veladec 1.3.0

快应用（Vela / 小米手环）`.rpk` → **`.jsc` QuickJS 字节码反编译器**。
零依赖、单文件可分发，一条命令把打包好的字节码还原成可读的伪 JS（保留 `goto`，能安全结构化的地方自动结构化成 `if/else`）。

```
$ ./veladec.pyz decompile app.rpk -o out/ --format html
// --- fn[36] decode(a0..a0) vars=6 stack=5 bc=227B
    if (a0) goto L0017;
L0017:
    r0 = (((a0("")).replace(/-/, "+")).replace(/_/, "/")).replace(/=+$/, "");
    r1 = [];
    r2 = 0;
    r4 = 0;
L0059:
    while (r4 < r0.length) {
        r5 = v0.indexOf(r0.charAt(r4));
        if (r5 < 0) {
            return null;
        }
    L008a:
        r3 = r3 << 6 | r5;
        r2 = r2 + 6;
        if (r2 >= 8) {
            r2 = r2 - 8;
        }
    L00cc:
        r4++;
    }
L00d6:
    return new Uint8Array(r1);
```

---

## 1. 能做什么 / 不做什么

| 能做 | 说明 |
|---|---|
| 解开 `.rpk` | 列出/导出包内所有文件，读 `manifest`（包名、版本、toolkit、features、pages） |
| 反编译 `.jsc` | 模块入口 + 全部函数体 → 伪 JS；表达式、运算符优先级、对象/数组字面量、`for...in`、`catch` 处理块都会还原 |
| 反汇编 | `disasm` 输出忠实指令清单（含 atom 名、跳转目标、cpool 常量），**这是最终依据** |
| 搜索 | `strings` / `search` 在 atom 表与常量池里按名/按正则找东西（找密钥、找文案、找协议字段） |
| 自检 | `selftest` 校验解码是否正确（指令边界、跳转落点、atom/cpool/槽位范围） |
| 多格式 | `js`（逐文件伪代码）/ `asm` / `json`（结构化，方便二次处理）/ `md` / `html`（自带搜索框的可浏览报告） |

**不做**：还原出可直接运行的源码级工程（变量名、类型、注释不可能恢复）；不绕过任何校验逻辑；不做重打包。

## 2. 安装

只需要 **Python 3.8+**，无第三方依赖。

三种用法任选：

```bash
# a) 单文件（推荐分发）
./veladec.pyz info app.rpk

# b) 源码目录
python3 veladec.py <命令> <目标>

# c) 装成全局命令
ln -s "$PWD/veladec.pyz" ~/.local/bin/veladec && veladec info app.rpk
```

## 3. 三十秒上手

```bash
./veladec.pyz info    app.rpk                        # 这是什么包、几张表、多少函数
./veladec.pyz ls      app.rpk --file pages/index     # 看包内文件
./veladec.pyz strings app.rpk --grep 激活            # 找关键字符串
./veladec.pyz decompile app.rpk -o out/              # 全量反编译成伪 JS
./veladec.pyz decompile app.rpk -o out/ --format html # 生成可点击/可搜索的 HTML 报告
```

直接对着单个 `.jsc` 或解包后的目录跑也可以：

```bash
./veladec.pyz decompile pages/index/index.jsc --fn 0 --stdout
```

## 4. 命令参考

| 命令 | 作用 | 常用参数 |
|---|---|---|
| `info <target>` | 指纹、文件清单、函数/指令统计、自动选表依据 | `-q` |
| `unpack <target> -o DIR` | 解包 `.rpk`（zip） | |
| `ls <target>` | 列出包内文件与大小 | `--file`, `--grep PAT` |
| `strings <target>` | 导出 atom 表 / 常量池字符串 | `--grep PAT`, `--file`, `--min N` |
| `search <target> PAT` | 在字节码引用位置搜索字符串 | `--regex` |
| `mv <target>` | **模块/视图地图**：入口、导出方法、字面量字段、闭包绑定、名字索引 | `--file`, `--fn N`, `--grep PAT`, `--names N`, `--format text\|json\|md`, `-o DIR` |
| `decompile <target>` | 反编译成伪 JS | `-o DIR`, `--format js\|json\|md\|html`, `--file`, `--fn N`, `--stdout`, `--single`, `--title`, `--no-structure`, `--no-labels`, `--offsets` |
| `disasm <target>` | 反汇编（忠实清单） | `-o DIR`, `--file`, `--fn N`, `--name`, `--stdout` |
| `run <target>` | **动态执行**：真跑一个函数，喂输入、读返回值、看平台调用 | `--fn N`, `--method NAME`, `--args JSON`, `--this JSON`, `--then FN[:ARGS]`, `--fill`, `--storage K=V`, `--device-id`, `--watch NAME`, `--watch-call FN`, `--trace`, `--snap FN@HEX[:N]`, `--atom ID=NAME`, `--json` |
| `selftest <target>` | 结构自检 | `--all-tables`（把 6 张表都跑一遍并对比） |
| `tables` | 打印内置 opcode 表/版本信息 | |

全局参数（写在子命令之前或之后均可）：`--atom-base N`（默认 `212`）、`--table auto|2020-11-08|…`（默认 `auto`）、`--builtins-file F`（自定义内置 atom 名表）、`-q`。

## 5. 输出长什么样

- **`js`**：一个 `.jsc` 一个 `*.pseudo.js`；`// --- fn[N] 名字(参数) vars= stack= bc=` 是函数头；`L00xx:` 是跳转标签（十六进制偏移）；行尾缩进即嵌套层级。
- **`asm`**：一行一条指令，列 = 偏移 / 助记符 / 操作数 / 注释（atom 名、跳转目标、cpool 常量）。末尾 `; exact=True len=NNN` 表示解码长度与函数头声明一致。
- **`json`**：`{files:[{name, atoms, functions:[{index,name,args,vars,stack,sig,lines,anoms}]}]}`，`anoms` 是渲染异常标记（如 `implicit-return`），便于批量筛查。
- **`html`**：单文件、离线、深色主题；顶部搜索框按函数名过滤，函数可折叠。

### 5.1 `mv`：先看地图，再读代码

反编译解决"这条指令什么意思"，**`mv` 解决"我该看哪个 `fn`"**。三个问题一次回答：入口导出了什么、页面/组件对象在哪、闭包变量到底绑到谁的槽位。

```
$ veladec mv app.rpk --file pages/index --grep dev

# pages/index/index.jsc   190 fns / 8750 insns
module   @aiot/index
exports  default
entry    fn[189] $k82 a0  v0  cl1  cp1       7i
view literal: fn[131] (15 fields, 11 methods)
  methods:
    classList                  fn[90]
    click                      fn[91]
  fields:
    __vm__                     = <?>
    state                      = null
name index   (w = 字段被写, r = 被读 / 被调用)
  devCode             w:fn[25],fn[80]
  devCodeText         w:fn[25],fn[80]  r:fn[169]

id       name                   arg var clos cpool size   xref
fn[  0] ?                      a1  v0  cl0  cp0       7i  calls: parse
```

- **entry / exports / methods**：模块入口那一个字面量里，`define_field` + `fclosure` 的字段是方法（直接给 `fn[N]`），常量字段是 `data` 初值。
- **闭包绑定**：按 `js_closure()` 的规则解析到底——
  `is_local` → 父函数变量槽 `r<n>`；`is_arg` → 父函数参数 `a<n>`；两者都没置 → 父函数闭包数组的第 `var_idx` 项，逐层上溯到最外层为止。
  于是 `v3 <- fn[80].r4 (salt)` 这种"到底抓了谁"的答案直接印出来，不用再手动对 `fclosure8` 与 `put_loc8`。
- **名字索引**：`get_field` / `put_field` / `get_field2;call_method` 落到 `fn` 粒度，`--grep` 直接过滤——找"谁写了 `devCode`"就是一行。
- **`--fn N`**：单函数详情 = 变量名表 + 闭包表（含 `flags` 逐位含义与解析结果）+ `cpool` 逐项（函数项直接标 `fn[k]`）+ 读写/调用/创建关系 + `made by`。

### 5.2 `run`：跑一遍，比读十遍准

静态分析回答"它大概在算什么"，`run` 回答"它到底算出了什么"。它是一台 QuickJS 字节码解释器 + 一套平台 API 桩，不需要设备、不需要改包。

```
# 真跑 sha256，跟 hashlib 对账
veladec run TARGET --file pages/index --fn 80 --args '[{},{}]' --fill require \
        --then '7:["abc"]'
# result: 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'

# 跑页面 onInit，把设备号喂进去，盯着关键变量
veladec run TARGET --file pages/index --fn 80 --args '[{},{}]' --fill require \
        --device-id B82TTQG0 --then 21 --watch devCode --watch expected
# watch put devCode   <- 'NDAB6NYG'      (fn[25]:0x0018)
# watch put expected  <- '841058703076'  (fn[25]:0x0053)

# 页面方法：--this 直接把页面 data 摆上去
veladec run TARGET --file pages/lock --fn 32 \
        --this '{"serial":"600192","z":"zyxw1","g":"z","h":"y","i":"x","j":"w"}'
# result: 4113216.0
```

要点：

- **`--fill require`**：模块工厂是 `(module, exports, require)`，缺的参数用真 `require` 补；`@app-module/system.*` 会自动接到宿主桩上，回调因此才会触发。
- **`--then FN[:ARGS]`**：入口跑完后，在它创建的闭包里找到 `fn[N]` 并调用，页面方法还会自动把所属对象字面量当 `this`。
- **`--watch NAME`** 盯 `put_loc` 写入，**`--watch-call FN`** 盯调用，**`--trace`** 全量指令流，**`--snap FN@HEX:N`** 在第 N 次经过某偏移时记一份局部变量快照（不中断）。
- **`--atom ID=NAME`**：内建 atom id 在不同 Vela 构建里会整体移位，运行时会按"接收者能不能实现这个方法"自动裁决并缓存；裁决错了就手动钉。
- 返回值同样可以 `--json` 拿，便于脚本化对账。

## 6. 它怎么工作的

### 6.1 文件格式（实测 + 官方源码对照）

`rpk` 就是 zip（多数字节 store 不压缩），`*.jsc` 是 QuickJS 的序列化产物：

```
[jsc]
  u8  BC 版本(本地样本 = 0x0f → 带 bytecode 的 module 记录起始)   ← 见下方说明
  ...
```

实际布局（`JS_WriteObjectAtoms`）：

1. `u8 version` → 本包字节码版本
2. `leb128 atom_count` → 原子表条目数
3. 每个 atom：`leb128 v`，`len = v >> 1`，`wide = v & 1`；`wide ? len*2 字节 UTF-16LE : len 字节 latin1`
4. 之后是对象记录（tag）：`15 = MODULE`（`module_name` atom、请求表、导出表、星导出、导入表、模块函数）、`14 = FUNCTION_BYTECODE`（flags/js_mode/名字/各计数/`vardefs`/闭包变量/字节码/行号表/常量池）

函数记录中**字节码在前、常量池在后**；指令里的 atom 操作数已被替换成 `表索引 + first_atom` 的裸 `u32`。

### 6.2 三个 Vela（快应用工具链）与官方 QuickJS 的差异

| 差异 | 官方 QuickJS | Vela 实测 | 处理 |
|---|---|---|---|
| 跳转操作数基准 | 相对当前指令 | **相对 `pos+1`**（`label8/label16` 恒相对；u32 形式两种都存在位） | 按 fmt 分策略 + 落点校验：`label8/16` 先试 `pos+1+sg`；u32 先试绝对值，再 `pos+1+sg`、`pos+sg` |
| atom 操作数基址 | `JS_ATOM_END`（224） | **212**（工具链裁掉了 12 个内置 atom） | `--atom-base`，默认 212 |
| `call_method` | 操作数带方法 atom | **不带**（方法名来自上一条 `get_field2`） | 用「方法标记」入栈跟踪接收者与方法名 |

内置 atom（`k < 212`，如 `Object`/`Array`/`Error`/`JSON`/`Math`）名字在 `veladec/builtins.py` 里，靠用法锚定（例如 `_interopRequireDefault` 的 `return {default: a0}` 定死 `22=default`）；没有定名的显示成 `$kNN` 并原样保留索引，不会瞎猜。

### 6.3 opcode 表：内置 6 个官方 release，自动选版本

`veladec/tables/` 内嵌 2019-07-09 / 2019-12-21 / 2020-01-19 / 2020-07-05 / 2020-11-08 / 2021-03-27 六个 release 的操作码表（含短操作码区），一个 release 一个模块，**运行时不需要任何 quickjs 源码**。

`--table auto`（默认）会对样本跑一次结构校验，按违规条数（penalty）选最小的表：

| 样本 | 2019-07-09 | 2019-12-21 | 2020-01-19 | 2020-07-05 | **2020-11-08** | 2021-03-27 |
|---|---|---|---|---|---|---|
| 地图 rpk（toolkit 2.0.5） | 5041 | 7932 | 5114 | 2125 | **0** | 0 |

判定差距是数量级的，`auto` 基本不会选错。个别包会在最优表上残留 1 条 `badatom`（内置 atom 名字表差异），不影响解码与反编译，`selftest` 里会如实列出。

## 7. 正确性自检

`selftest` 检查四件事：每条指令是否恰好落在合法边界、全函数解码长度是否等于 `byte_code_len`、跳转目标是否落在指令起始、atom/cpool/loc/arg 引用是否越界。

```
$ ./veladec.pyz selftest map-v1.0.226.rpk
2020-11-08   funcs=2208  insns=129442  penalty=0  not_exact=0  unknown=0
             badjump=0   badatom=0    badpool=0   badslot=0
selftest: OK
```

逐文件（地图样本）：app 663 fn / 41827 ins、index 123/17727、mapview 444/28998、dnav 158/9066、trace 320/14360、demo 150/6123、settings 120/3856、sync 95/3309、auth 72/2011、marks 63/2165。**2208 个函数 100% 定长解码，零越界引用。**

## 8. 局限（请连同 .asm 一起看）

1. **伪代码是"恢复出来的表达式"，不是源码**：`dup/insert/swap` 密集的三目、链式 `&&/||`、解构处仍可能出现 `?` 或临时变量赋值。以 `disasm` 为准。
2. **控制流只做保守结构化**：
   - `if / else`：仅当前向条件跳转的目标只有 **1 个**引用、且不成对出现短路口（`dup;if_true;drop`）时才折叠；共享的失败出口一律保留 `goto`（这也是「守卫链」最忠实的写法）。
   - `while`：仅当存在回边 `goto L` 且 `L` 到回边之间恰有一个条件跳转正好跳回边之后时折叠，其余循环保持 `goto` 形式。
   - `try / catch`：用注释标出边界（`// try {` … `// } catch (exc..) {`），不生成花括号块；异常值以 `exc000c` 之类的变量进入表达式流。
   - `for`：`for...in / for...of` 已按迭代器语义还原；C 风格 `for` 仍呈现为 `while` + `goto`。
3. **不重命名**：局部变量就是 `r0/r1…`，闭包变量 `v0…`，参数 `a0…`。名字来自函数头或被 Terser 压掉的，显示成 `<null>`。
4. **不还原类型与类型推断**，不做死代码消除。
5. **版本相关**：只对 Vela toolkit 2.0.5 产物验证过；换工具链大版本时 opcode 表与 `atom_base` 可能需要重标定（见 §9）。

## 9. 遇到新工具链怎么补

1. `./veladec.pyz selftest --all-tables new.rpk` —— 看哪张表 penalty 最低。
2. 若全都很高：取对应 release 的 `quickjs-opcode.h`，用 `tools/gen_tables.py --src <放源码树的目录>` 生成新模块放进 `veladec/tables/`。
3. 若 atom 名字整体偏移：用「字段位的 atom 必须是标识符」做扫描，二分 `--atom-base`，正确值处 ident 比例会跳到 1.0（脚本见 `tools/calib_atom_base.py`）。
4. 若跳转整体错位：`--no-structure` 先看 `.asm`，确认是相对/绝对基准问题再改 `ins.resolve_label`。

## 10. 目录

每个模块控制在 500 行以内：数据（opcode 表）一版一文件，逻辑按职责拆包。

```
veladec/                    # 源码包
  cli/                      # 命令行
    __init__.py             #   argparse 定义 + main()
    options.py              #   选项对象、目标加载、自动选表
    asm.py                  #   指令列表（反汇编文本）
    formats.py              #   js / md / json / html 四种输出
    commands.py             #   info / unpack / ls / strings / search / selftest / tables
    decompile_cmd.py        #   decompile / disasm
  decomp/                   # 反编译：线性栈恢复 + 保守结构化
    __init__.py             #   对外只暴露 FuncRenderer / decompile_file / jsstr
    expr.py                 #   字面量、优先级、栈值渲染
    structure.py            #   跳转目标、span 发现、if/else、try/catch
    dispatch.py             #   逐 opcode 翻译表
    renderer.py             #   FuncRenderer 主循环
  tables/                   # 6 个 release 的 opcode / atom 表（自动生成，一版一模块）
    __init__.py             #   汇总成 OPCODE_TABLES / ATOM_TABLES
    v2019_07_09.py          #   K / PRE / SHORT / ATOMS
    v2019_12_21.py
    v2020_01_19.py
    v2020_07_05.py
    v2020_11_08.py
    v2021_03_27.py
  ser.py                    # .jsc 序列化解析
  ins.py                    # opcode 表 / 解码 / 跳转解析 / 校验
  builtins.py               # 内置 atom 名表
  rpk.py                    # rpk / 目录 / 单文件目标解析
  rt/                       # 动态执行：values / host / interp / atoms
veladec.py                  # 入口
veladec.pyz                 # 单文件可执行（无需安装）
examples/                   # 两个真实样本的输出片段
tools/                      # 表生成与标定脚本
```

## 11. 版本

- **1.3.0** — 新增 `run` 子命令（动态执行）：QuickJS 字节码解释器 `veladec/rt/`（`values` / `host` / `interp` / `atoms`）+ 平台 API 桩（`storage` / `device` / `router` / `vibrator` / `showToast` / `Date` / `Math` / `JSON` / `RegExp`），支持 `--args` / `--this` / `--then` / `--fill` / `--watch` / `--watch-call` / `--trace` / `--snap` / `--stop-at` / `--atom` / `--json`。附带 `skills/vela-reverse/SKILL.md` 与两份提示词（一键逆向、skill 安装）。
  修掉的两个真实 bug：**tagged-int atom**（`0x80000000+n` 是整型属性名 `"n"`，此前被当成 `$kNN` 内置名，导致 64 项常量表只装上 32 项）与**字符串下标**（`"abc"[1]` 走了方法表，返回 `undefined`）。
  实测对账：两个样本 `selftest: OK`；`sha256('abc')` 与 hashlib 逐字节相同；函数求解器 `devCode/expected` 与 hashlib 独立复算一致；羊了个羊 `decrypt(600192) = 4113216`。
- **1.2.0** — 新增 `mv` 子命令（模块/视图地图）：入口与导出方法、对象字面量的字段/方法归类、**闭包变量的逐层绑定解析**、字段与方法的 `fn` 级名字索引（`--grep`）、单函数详情（`vars` / `closures` / `cpool` / `writes` / `reads` / `calls` / `makes` / `made by`），输出 `text|json|md`。反编译与反汇编输出不变。
- **1.1.0** — 纯结构整理，**功能与输出完全不变**（对地图样本逐字节比对过 13 条命令的输出）：`cli.py` / `decomp.py` / `tables.py` 三个大文件拆成包，最大模块从 2877 行降到 496 行；`tables/` 一版一模块，`tools/gen_tables.py` 改为生成该包并支持增量合并；新增 `LICENSE`。
- **1.0.0** — 首个可分发版本：rpk 解包 / 反编译 / 反汇编 / 搜索 / 自检 / 四种格式；三处 Vela 差异处理；6 张 opcode 表 + 自动选表；优先级括号、对象/数组字面量、`for...in`、`while` 循环恢复、`catch` 处理块、隐式尾 `return`、方法调用接收者括号化，以及 `veladec.pyz` 单文件分发。
  实测（地图样本 10 文件 / 2208 函数 / 129442 指令）：全量反编译 **1.8 秒**；伪代码 `goto` 从 1173 条降到 1047 条、无法恢复的 `?` 占位从 324 处降到 92 处（剩余均为不可达的 rethrow 尾巴）。

---
仅用于自有或已获授权的快应用静态分析。
