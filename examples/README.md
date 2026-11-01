# examples/

用真实快应用包跑出来的样例（`veladec.pyz` 1.1.0）。样本是 10 个页面的地图类应用（toolkit 2.0.5，2208 个函数 / 129442 条指令）。

| 文件 | 来源命令 | 看点 |
|---|---|---|
| `1-info-map-rpk.txt` | `veladec.pyz info app.rpk` | 包指纹、文件清单、函数/指令统计、`--table auto` 的选表依据 |
| `2-selftest-map.txt` | `veladec.pyz selftest app.rpk` | 结构自检：penalty / not_exact / badjump / badatom 全 0 |
| `3-pseudo-decode.js` | `decompile … --file app.jsc --fn 36` | 单个函数的伪代码：base64url 解码器，含 `while` 循环恢复 |
| `4-map-auth.pseudo.js` | `decompile … --file pages/auth/auth.jsc` | 整页伪代码（620+ 行） |
| `5-sync-fn1.asm` | `disasm … --file pages/sync/sync.jsc --fn 1` | 反汇编格式：偏移 / 助记符 / 操作数 / 注释（atom 名、跳转目标） |
| `6-strings-grep.txt` | `strings … --grep license` | 按关键字定位 atom 索引（找协议字段、文件名、文案） |
| `7-map-auth-report.html` | `decompile … --format html` | 离线可搜索 HTML 报告（浏览器直接打开） |

`3-pseudo-decode.js` 全文：

```js
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

对照 `5-sync-fn1.asm` 可以看到同一段逻辑在指令层的样子：`get_var_ref → get_field2 → push_atom_value → call_method n:N` 逐条对应。
伪代码里的每个运算符、每层括号都能在 `.asm` 里找到对应指令——这也是为什么把 `.asm` 当作最终依据。
