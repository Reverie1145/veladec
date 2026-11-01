"""Bytecode -> readable pseudo-JS.

The decompiler is a *linear stack-expression recovery* pass with a light
control-flow structurer on top:

  * forward conditional jumps become `if (c) { ... }` / `if (c) { ... } else { ... }`
  * `try` handlers (`catch` opcode) are annotated instead of guessed
  * everything else keeps an explicit `goto Lxxxx` so the output stays faithful

Expression recovery is best-effort: where the operand stack model drifts (dense
dup/insert sequences from `&&`, `||`, `?:`), a `?` placeholder is emitted and
counted as an anomaly.  The instruction listing (`--format asm`) is authoritative.

Layout:
  expr.py       literal/precedence formatting and stack-value rendering
  structure.py  jump targets, span discovery, if/else and try/catch
  dispatch.py   the per-opcode translation table
  renderer.py   FuncRenderer, which drives the pass
"""

from .expr import jsstr
from .renderer import FuncRenderer, Line, decompile_file


__all__ = ["FuncRenderer", "Line", "decompile_file", "jsstr"]
