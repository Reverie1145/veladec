"""Bytecode -> readable pseudo-JS.

The decompiler is a *linear stack-expression recovery* pass with a light
control-flow structurer on top:

  * forward conditional jumps become `if (c) { ... }` / `if (c) { ... } else { ... }`
  * `try` handlers (`catch` opcode) are annotated instead of guessed
  * everything else keeps an explicit `goto Lxxxx` so the output stays faithful

Expression recovery is best-effort: where the operand stack model drifts (dense
dup/insert sequences from `&&`, `||`, `?:`), a `?` placeholder is emitted and
counted as an anomaly.  The instruction listing (`--format asm`) is authoritative.
"""

import re
import struct

from .ins import OpTable, resolve_label, JUMP_FMTS

BIN = {
    'add': '+', 'sub': '-', 'mul': '*', 'div': '/', 'mod': '%', 'pow': '**',
    'and': '&', 'or': '|', 'xor': '^', 'shl': '<<', 'sar': '>>', 'shr': '>>>',
    'lt': '<', 'lte': '<=', 'gt': '>', 'gte': '>=', 'eq': '==', 'neq': '!=',
    'strict_eq': '===', 'strict_neq': '!==', 'instanceof': 'instanceof', 'in': 'in',
}
UN = {'neg': '-', 'plus': '+', 'not': '~', 'lnot': '!', 'typeof': 'typeof '}
# In Vela builds `not` is bitwise (~) and `lnot` is logical (!) -- verified by
# usage counts (8 vs 723 occurrences) and by operand types.
UN_SWAP = {}

KEYWORDS = ('if', 'else', 'while', 'for', 'return', 'throw', 'try', 'catch',
            'new', 'typeof', 'delete', 'in', 'instanceof', 'null', 'undefined',
            'true', 'false', 'this', 'function', 'var', 'let', 'const')


def jsstr(v):
    if isinstance(v, str):
        out = []
        for ch in v:
            if ch == '\\':
                out.append('\\\\')
            elif ch == '"':
                out.append('\\"')
            elif ch == '\n':
                out.append('\\n')
            elif ch == '\r':
                out.append('\\r')
            elif ch == '\t':
                out.append('\\t')
            elif ord(ch) < 0x20 or ord(ch) == 0x7f:
                out.append('\\x%02x' % ord(ch))
            else:
                out.append(ch)
        return '"' + ''.join(out) + '"'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if v is None:
        return 'null'
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return repr(v)


PREC = {'||': 1, '&&': 2, '|': 3, '^': 4, '&': 5,
        '==': 6, '!=': 6, '===': 6, '!==': 6,
        '<': 7, '<=': 7, '>': 7, '>=': 7, 'instanceof': 7, 'in': 7,
        '<<': 8, '>>': 8, '>>>': 8, '+': 9, '-': 9, '*': 10, '/': 10,
        '%': 10, '**': 11}


def _scan_top_ops(expr):
    """Yield (index, operator) for operators at bracket depth 0."""
    depth = 0
    quote = None
    i = 0
    n = len(expr)
    ops = sorted(PREC, key=len, reverse=True)
    while i < n:
        ch = expr[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in '"\'':
            quote = ch
            i += 1
            continue
        if ch in '([{':
            depth += 1
            i += 1
            continue
        if ch in ')]}':
            depth -= 1
            i += 1
            continue
        if depth == 0:
            for op in ops:
                if expr.startswith(op, i):
                    yield i, op
                    i += len(op)
                    break
            else:
                i += 1
            continue
        i += 1


def top_prec(expr):
    if not isinstance(expr, str):
        return 99
    found = [PREC[op] for _i, op in _scan_top_ops(expr)]
    return min(found) if found else 99


NEG = {'==': '!=', '!=': '==', '===': '!==', '!==': '===', '>': '<=', '<': '>=',
       '>=': '<', '<=': '>'}


def negate(e):
    if not isinstance(e, str):
        return '!%s' % e
    if e.startswith('!') and not e.startswith('!='):
        return e[1:] if not e[1:2].isalnum() else '!(%s)' % e
    ops = list(_scan_top_ops(e))
    if len(ops) == 1:
        i, op = ops[0]
        if op in NEG:
            return '%s %s %s' % (e[:i].rstrip(), NEG[op], e[i + len(op):].lstrip())
    return '!(%s)' % e


def binary(x, op, y):
    p = PREC.get(op, 99)
    left = x if top_prec(x) > p else '(%s)' % x
    right = y if top_prec(y) >= p else '(%s)' % y
    return '%s %s %s' % (left, op, right)


ATOMIC_RE = re.compile(r'^(?:[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\[[^\]]*\])*'
                       r'|"[^"]*"|/[^/\n]*/[a-z]*|\d+(?:\.\d+)?|<fn:[^>]*>)$')


def atomic(e):
    return bool(isinstance(e, str) and ATOMIC_RE.match(e))


def paren(e):
    return e if atomic(e) else '(%s)' % e


def call_expr(recv, args, name=None):
    a = ', '.join(args)
    if name is None:
        return '%s(%s)' % (paren(recv), a)
    return '%s.%s(%s)' % (paren(recv), name, a)


def render_val(v):
    if isinstance(v, dict):
        if '__text__' in v:
            return v['__text__']
        if '__ol__' in v:
            return '{' + ', '.join('%s: %s' % (k, render_val(x)) for k, x in v['__ol__']) + '}'
        if '__al__' in v:
            return '[' + ', '.join(render_val(x) for x in v['__al__']) + ']'
        if '__m__' in v:
            return '%s.%s' % (paren(render_val(v['__recv__'])), v['__m__'])
        return str(v)
    return v


class Line:
    """One emitted source line (indent depth + text), for txt/json/html output."""
    __slots__ = ('depth', 'text', 'pos')

    def __init__(self, depth, text, pos=None):
        self.depth = depth
        self.text = text
        self.pos = pos


class FuncRenderer:
    def __init__(self, jsc, ops, f, opts, index=None):
        self.j = jsc
        self.d = ops
        self.f = f
        self.o = opts
        self.index = index
        self.bc = f['bytecode']
        self.ins, self.ok, self.exact = ops.decode(self.bc)
        self.ncp = len(f['cpool'])
        self.starts = {i.pos for i in self.ins}
        self.lines = []
        self.st = []
        self.dup_pending = False
        self.skip_drop = False
        self.iter_name = None
        self.f2 = None
        self.anoms = []
        self.refs = self._count_refs()
        self.spans = self._find_spans()

    # ------------------------------------------------------------- helpers
    def _count_refs(self):
        refs = {}
        for i in self.ins:
            if i.fmt in JUMP_FMTS:
                t = resolve_label(self.ins, i.pos, i.extra[1], i.fmt)
                if t is not None:
                    refs[t] = refs.get(t, 0) + 1
        return refs

    def target(self, ins):
        if ins.fmt not in JUMP_FMTS:
            return None
        return resolve_label(self.ins, ins.pos, ins.extra[1], ins.fmt)

    def label(self, pos):
        return 'L%04x' % pos

    def _exc_name(self, pos):
        return 'exc' if self.handlers.get(pos) is None else 'exc%d' % self.handlers[pos]

    def _prev_ins(self, pos):
        prev = None
        for i in self.ins:
            if i.pos >= pos:
                break
            prev = i
        return prev

    def _find_spans(self):
        """Forward conditional jumps that can be rendered as if/else blocks."""
        spans = {}
        for i in self.ins:
            base, _ = self.d.normalize(i.name)
            if base not in ('if_true', 'if_false'):
                continue
            t = self.target(i)
            if t is None or t <= i.next:
                continue
            if self.refs.get(t, 0) != 1:
                continue
            prev = self._prev_ins(i.pos)
            if prev is not None and self.d.normalize(prev.name)[0] == 'dup':
                continue
            body_lo, body_hi = i.next, t
            if body_lo >= body_hi:
                continue
            spans[i.pos] = {'lo': body_lo, 'hi': body_hi, 'invert': base == 'if_true',
                            'else_lo': None, 'else_hi': None}
        # if/else: then-body ends with `goto L3` past the else block
        by_pos = {i.pos: i for i in self.ins}
        self.excvar = None
        self.nolabel = None
        self.loops = {}
        for i in self.ins:
            base, _ = self.d.normalize(i.name)
            if base != 'goto':
                continue
            t = self.target(i)
            if t is None or t >= i.pos:
                continue
            head = None
            for c in self.ins:
                if t <= c.pos < i.pos:
                    cb, _ = self.d.normalize(c.name)
                    if cb in ('if_true', 'if_false') and self.target(c) == i.next:
                        head = c
                        break
            if head is None:
                continue
            body_lo, body_hi = head.next, i.pos
            if body_lo >= body_hi:
                continue
            self.loops[t] = {'cond_pos': head.pos, 'cond_invert': None,
                             'body_lo': body_lo, 'body_hi': body_hi, 'end': i.next}
        self.handlers = {}
        for i in self.ins:
            base, _ = self.d.normalize(i.name)
            if base != 'catch':
                continue
            t = self.target(i)
            if t is not None and t > i.pos:
                self.handlers.setdefault(t, i.pos)
        self.suppressed = set()
        for start, sp in list(spans.items()):
            last = None
            for i in self.ins:
                if sp['lo'] <= i.pos < sp['hi']:
                    last = i
            if last is None:
                continue
            base, _ = self.d.normalize(last.name)
            if base != 'goto':
                continue
            t3 = self.target(last)
            if t3 is None or t3 <= sp['hi']:
                continue
            if self.refs.get(sp['hi'], 0) != 1:
                continue                      # else block shared with other jumps
            if not (sp['hi'] < t3 <= len(self.bc)):
                continue
            sp['else_lo'], sp['else_hi'] = sp['hi'], t3
            self.suppressed.add(last.pos)
        return spans

    def emit(self, text, pos=None, depth=None):
        self.lines.append(Line(self.o.indent if depth is None else depth, text, pos))

    def cp(self, i):
        if not (0 <= i < self.ncp):
            return 'c%d?' % i
        v = self.f['cpool'][i]
        if isinstance(v, dict):
            return '<fn:%s>' % (v.get('name') or 'anon')
        return jsstr(v)

    def atom(self, k, value=False):
        j = self.j
        if isinstance(k, tuple):
            return str(k[1])
        raw = k
        flag = bool(raw & 0x80000000)
        kk = raw & 0x7fffffff
        if kk < j.atom_base:
            nm = self.o.builtins.get(kk) or '$k%d' % kk
            return jsstr(nm) if value else nm
        i = kk - j.atom_base
        nm = j.atoms[i] if 0 <= i < len(j.atoms) else '<bad atom %d>' % i
        if value:
            return jsstr(nm)
        return ('~' + nm) if flag else nm

    def pop(self, n=1):
        out = []
        for _ in range(n):
            if not self.st:
                self.anoms.append('empty-stack')
                out.append('?')
            else:
                out.append(render_val(self.st.pop()))
        return out[::-1]

    def P(self, x):
        self.st.append(x)

    def top(self, k=1):
        if len(self.st) < k:
            self.anoms.append('stack-underflow')
            return '?'
        return render_val(self.st[-k])

    # ------------------------------------------------------------ rendering
    def render(self):
        if self.o.offsets:
            self.emit('// %s' % self.signature())
        depth = self.o.indent
        hi = len(self.bc)
        self.render_range(0, hi, depth)
        if self.st:
            # expression-bodied function: Vela omits the trailing `return`
            tail = render_val(self.st[-1])
            last = self.lines[-1].text.strip() if self.lines else ''
            if not last.startswith('return'):
                self.anoms.append('implicit-return')
                self.emit('return %s;' % tail, depth=depth)
        return self.lines

    def signature(self):
        f = self.f
        name = f['name'] or '<anon>'
        return 'fn[%s] %s(a0..a%d) vars=%d stack=%d bc=%dB%s' % (
            self.index, name, max(f['arg_count'] - 1, 0), f['var_count'],
            f['stack_size'], f['byte_code_len'],
            '' if self.exact else '  [DECODE MISMATCH]')

    def render_range(self, lo, hi, depth):
        pos = lo
        ins_by_pos = {i.pos: i for i in self.ins}
        while pos < hi:
            ins = ins_by_pos.get(pos)
            if ins is None:
                pos += 1
                continue
            if pos in self.handlers:
                self.emit('// } catch (%s) {  (try at %s)'
                          % (self._exc_name(pos), self.label(self.handlers[pos])), pos, depth)
                self.P(self._exc_name(pos))
            # close blocks that end here
            if (self.o.labels and pos != self.nolabel
                    and (pos in self.refs or self._is_block_boundary(pos))):
                self.emit_label(pos, depth)
            lp = self.loops.get(pos) if self.o.structure else None
            if lp is not None and lp['end'] <= hi:
                if lp['cond_pos'] > pos:
                    self.nolabel = pos
                    self.render_range(pos, lp['cond_pos'], depth)
                    self.nolabel = None
                cond_ins = next(c for c in self.ins if c.pos == lp['cond_pos'])
                invert = self.d.normalize(cond_ins.name)[0] == 'if_true'
                cond = self.pop()[0] if self.st else '?'
                self.emit('while (%s) {' % (negate(cond) if invert else cond),
                          pos, depth)
                self.render_range(lp['body_lo'], lp['body_hi'], depth + 1)
                self.emit('}', depth=depth)
                pos = lp['end']
                continue
            sp = self.spans.get(pos) if self.o.structure else None
            if sp and sp['hi'] <= hi:
                self._render_if(sp, depth)
                pos = sp['else_hi'] or sp['hi']
                continue
            if pos in self.suppressed:
                pos = ins.next
                continue
            self.dispatch(ins, depth)
            pos = ins.next

    def _is_block_boundary(self, pos):
        return any(sp['hi'] == pos or sp.get('else_hi') == pos
                   for sp in self.spans.values())

    def emit_label(self, pos, depth):
        tag = ''
        if self.refs.get(pos, 0) > 1:
            tag += '   // %d refs' % self.refs[pos]
        self.lines.append(Line(max(depth - 1, 0), self.label(pos) + ':' + tag))

    def catch_targets(self):
        out = set()
        for i in self.ins:
            base, _ = self.d.normalize(i.name)
            if base in ('catch', 'gosub'):
                t = self.target(i)
                if t is not None:
                    out.add(t)
        return out

    def _render_if(self, sp, depth):
        cond = self.pop()[0]
        if sp['invert']:
            test = cond[1:] if cond.startswith('!') else '!(%s)' % cond
        else:
            test = cond
        self.lines.append(Line(depth, 'if (%s) {' % test))
        self.render_range(sp['lo'], sp['hi'], depth + 1)
        if sp['else_lo'] is not None:
            self.lines.append(Line(depth, '} else {'))
            self.render_range(sp['else_lo'] + self._size_at(sp['else_lo']),
                              sp['else_hi'], depth + 1)
        self.lines.append(Line(depth, '}'))

    def _size_at(self, pos):
        for i in self.ins:
            if i.pos == pos:
                return i.size
        return 1

    # ------------------------------------------------------------- opcodes
    def dispatch(self, ins, depth):
        pos, size, fmt, ex = ins.pos, ins.size, ins.fmt, ins.extra
        name = ins.name
        b, argc_hint = self.d.normalize(name)
        P, pop, em = self.P, self.pop, lambda t: self.emit(t, pos, depth)

        # ---- constants
        if b == 'push_this':
            return P('this')
        if b == 'push_null':
            return P('null')
        if b == 'push_undefined':
            return P('undefined')
        if b == 'push_true':
            return P('true')
        if b == 'push_false':
            return P('false')
        if b == 'push_empty_string':
            return P('""')
        if b == 'push_i32':
            return P(str(struct.unpack_from('<i', self.bc, pos + 1)[0]))
        if b in ('push_i8',):
            return P(str(struct.unpack_from('<b', self.bc, pos + 1)[0]))
        if b in ('push_i16',):
            return P(str(struct.unpack_from('<h', self.bc, pos + 1)[0]))
        if b == 'push_const':
            idx = ex[1] if ex else 0
            v = self.f['cpool'][idx] if 0 <= idx < self.ncp else None
            if isinstance(v, dict):
                return P('<fn:%s>' % (v.get('name') or 'anon'))
            return P({'__const__': idx, '__raw__': v, '__text__': jsstr(v)})
        if b == 'push_atom_value':
            return P(self.atom(ex[1], value=True))
        if ex and ex[0] == 'imm' and fmt == 'none_int':
            return P(str(ex[1]))

        # ---- slots
        if b in ('get_loc', 'get_arg', 'get_var_ref'):
            idx = ex[1] if ex and ex[0] in ('loc', 'arg', 'varref') else argc_hint
            pref = {'get_loc': 'r', 'get_arg': 'a', 'get_var_ref': 'v'}[b]
            return P('%s%s' % (pref, idx))
        if b in ('put_loc', 'set_loc', 'put_arg', 'put_var_ref'):
            idx = ex[1] if ex and ex[0] in ('loc', 'arg', 'varref') else argc_hint
            pref = {'put_loc': 'r', 'set_loc': 'r', 'put_arg': 'a',
                    'put_var_ref': 'v'}[b]
            val = self.top() if b == 'set_loc' else pop()[0]
            if isinstance(val, str) and val.startswith('exc'):
                self.excvar = '%s%s' % (pref, idx)
            if val in ('%s%s++' % (pref, idx), '%s%s--' % (pref, idx),
                       '++%s%s' % (pref, idx), '--%s%s' % (pref, idx)):
                return em('%s;' % val)
            return em('%s%s = %s;' % (pref, idx, val))
        if b in ('inc_loc', 'dec_loc', 'add_loc'):
            idx = ex[1] if ex else '?'
            if b == 'inc_loc':
                return em('r%s++;' % idx)
            if b == 'dec_loc':
                return em('r%s--;' % idx)
            return em('r%s += %s;' % (idx, pop()[0]))
        if b == 'special_object':
            # Vela: object with a dedicated exotic kind (arguments/array/...);
            # the atom operand names the kind.
            return P('/* %s */ {}' % (self.atom(ex[1]) if ex else 'special'))
        if b == 'set_arg':
            idx = ex[1] if ex else argc_hint
            val = pop()[0]
            if val in ('a%s++' % idx, 'a%s--' % idx, '++a%s' % idx, '--a%s' % idx):
                return em('%s;' % val)
            return em('a%s = %s;' % (idx, val))
        if b == 'ret':
            if self.st:
                return em('return %s;' % pop()[0])
            return em('return;')
        if b == 'set_loc_uninitialized':
            return em('r%s = undefined;' % (ex[1] if ex else '?'))
        if b in ('put_loc_check', 'put_loc_check_init'):
            idx = ex[1] if ex else '?'
            val = pop()[0]
            if val in ('r%s++' % idx, 'r%s--' % idx, '++r%s' % idx, '--r%s' % idx):
                return em('%s;' % val)
            return em('r%s = %s;' % (idx, val))
        if b in ('get_loc_check',):
            return P('r%s' % (ex[1] if ex else '?'))
        if b in ('get_var_ref_check',):
            return P('v%s' % (ex[1] if ex else '?'))
        if b in ('put_var_ref_check',):
            return em('v%s = %s;' % (ex[1] if ex else '?', pop()[0]))
        if b in ('get_var', 'get_var_undef'):
            return P(self.atom(ex[1]))
        if b == 'put_var':
            return em('%s = %s;' % (self.atom(ex[1]), pop()[0]))
        if b == 'delete_var':
            return em('delete %s;' % self.atom(ex[1]))

        # ---- properties
        if b == 'get_field':
            return P('%s.%s' % (pop()[0], self.atom(ex[1])))
        if b == 'get_field2':
            name = self.atom(ex[1])
            recv = self.st.pop() if self.st else '?'
            self.f2 = name
            return P({'__m__': name, '__recv__': recv})
        if b == 'get_field_opt_chain':
            return P('%s?.%s' % (self.top(), self.atom(ex[1])))
        if b == 'put_field':
            v, o = pop(2)
            return em('%s.%s = %s;' % (o, self.atom(ex[1]), v))
        if b in ('define_field', 'define_field2'):
            v = pop()[0]
            o = self.st[-1] if self.st else None
            if isinstance(o, dict) and '__ol__' in o:
                o['__ol__'].append((self.atom(ex[1]), v))
                return
            o = pop()[0]
            return em('%s.%s = %s;' % (o, self.atom(ex[1]), v)) or P(o)
        if b == 'get_array_el' or b == 'get_array_el2':
            i = pop()[0]
            if b == 'get_array_el':
                o = pop()[0]
            else:
                o = self.top()
            return P('%s[%s]' % (o, i))
        if b == 'put_array_el':
            o, i, v = pop(3)
            return em('%s[%s] = %s;' % (o, i, v))
        if b == 'define_array_el':
            v = pop()[0]
            o = self.st[-1] if self.st else None
            if isinstance(o, dict) and '__al__' in o:
                o['__al__'].append(v)
                return
            o = pop()[0]
            return em('%s.push(%s);' % (o, v))
        if b == 'append':
            v, o = pop(2)
            return em('%s += %s;' % (o, v))
        if b == 'get_length':
            return P('%s.length' % pop()[0])

        # ---- calls
        if b in ('call', 'tail_call', 'eval', 'call_constructor'):
            argc = self._argc(ins, argc_hint)
            args = pop(argc) if argc else []
            callee = pop()[0]
            txt = '%s(%s)' % (callee, ', '.join(args))
            return P('new ' + txt if b == 'call_constructor' else txt)
        if b in ('call_method', 'tail_call_method'):
            argc = self._argc(ins, argc_hint)
            args = pop(argc) if argc else []
            if ex and ex[0] == 'atom' and (ex[1] & 0x7fffffff) >= self.j.atom_base:
                return P(call_expr(pop()[0], args))
            mk = self.st.pop() if self.st else '?'
            if isinstance(mk, dict) and '__m__' in mk:
                recv, name = mk['__recv__'], mk['__m__']
            else:
                recv, name = render_val(mk), (self.f2 or '?')
            return P(call_expr(recv, args, name))
        if b == 'apply':
            args, obj, fn = pop(3)
            return P('%s.apply(%s, %s)' % (fn, obj, args))
        if b == 'fclosure':
            return P(self.cp(ex[1] if ex else 0))
        if b == 'set_name':
            if self.st and isinstance(self.st[-1], str) and self.st[-1].startswith('<fn:'):
                self.st[-1] = '<fn:%s>' % self.atom(ex[1])
            return
        if b == 'define_method':
            v = pop()[0]
            o = pop()[0]
            em('%s.%s = %s;' % (o, self.atom(ex[1]), v))
            return P(o)

        # ---- objects / arrays
        if b == 'object':
            return P({'__ol__': []})
        if b == 'array_from':
            n = self._argc(ins, None)
            items = pop(n) if n else []
            return P({'__al__': items})
        if b == 'regexp':
            fe = self.st.pop() if self.st else None
            pe = self.st.pop() if self.st else None
            praw = pe.get('__raw__') if isinstance(pe, dict) else None
            fraw = fe.get('__raw__') if isinstance(fe, dict) else None
            if isinstance(praw, str):
                fl = fraw if isinstance(fraw, str) and re.fullmatch(r'[a-z]*', fraw) else ''
                return P('/%s/%s' % (praw, fl))
            return P('/(%s)/%s' % (render_val(pe), render_val(fe)))

        # ---- control
        if b in ('if_true', 'if_false'):
            cond = pop()[0]
            t = self.target(ins)
            L = self.label(t) if t is not None else 'lbl:%d' % ins.extra[1]
            if self.dup_pending:
                self.dup_pending = False
                self.skip_drop = True
            if b == 'if_false':
                return em('if (%s) goto %s;' % (negate(cond), L))
            return em('if (%s) goto %s;' % (cond, L))
        if b == 'goto':
            t = self.target(ins)
            return em('goto %s;' % (self.label(t) if t is not None else 'lbl:%s' % ins.text))
        if b == 'catch':
            t = self.target(ins)
            if t is not None and t > pos:
                return self.emit('// try {  (catch at %s)' % self.label(t), pos, depth)
            return self.emit('// catch (handler -> %s)'
                             % (self.label(t) if t is not None else '?'), pos, depth)
        if b == 'gosub':
            t = self.target(ins)
            return em('gosub %s;' % (self.label(t) if t is not None else '?'))
        if b == 'return':
            return em('return %s;' % pop()[0])
        if b == 'return_undef':
            return em('return;')
        if b == 'throw':
            if self.st:
                return em('throw %s;' % pop()[0])
            # dead rethrow path: reuse the exception variable bound in this handler
            return em('throw %s;' % (self.excvar or '?'))

        # ---- stack juggling
        if b == 'drop':
            if self.skip_drop:
                self.skip_drop = False
                return
            pop()
            return
        if b == 'nip':
            v = pop()[0]
            pop()
            return P(v)
        if b.startswith('dup'):
            n = 1 if b == 'dup' else int(b[-1])
            if len(self.st) >= n:
                for k in range(n):
                    P(self.st[len(self.st) - n])
            self.dup_pending = True
            return
        if b == 'swap':
            a, c = pop(2)
            P(c)
            return P(a)
        if b == 'insert2':
            a, c = pop(2)
            P(a)
            P(c)
            return P(a)
        if b == 'insert3':
            if len(self.st) >= 3:
                self.st.insert(len(self.st) - 3, self.st[-1])
            return
        if b == 'insert4':
            if len(self.st) >= 4:
                self.st.insert(len(self.st) - 4, self.st[-1])
            return
        if b == 'rot3l':
            if len(self.st) >= 3:
                self.st[-3], self.st[-2], self.st[-1] = self.st[-2], self.st[-1], self.st[-3]
            return
        if b == 'rot3r':
            if len(self.st) >= 3:
                self.st[-3], self.st[-2], self.st[-1] = self.st[-1], self.st[-3], self.st[-2]
            return
        if b in ('perm3', 'perm4', 'perm5'):
            return

        # ---- unary / binary
        if b in UN_SWAP:
            return P(UN_SWAP[b] + pop()[0])
        if b in UN:
            return P(UN[b] + pop()[0])
        if b == 'delete':
            return P('delete ' + pop()[0])
        if b in ('inc', 'dec', 'post_inc', 'post_dec'):
            o = pop()[0]
            return P(('++' if b == 'inc' else '--') + o if b in ('inc', 'dec')
                     else o + ('++' if b == 'post_inc' else '--'))
        if b in ('is_undefined', 'is_null', 'is_undefined_or_null', 'is_function',
                 'is_object', 'is_array', 'is_error'):
            return P('%s(%s)' % (b, pop()[0]))
        if b in BIN:
            x, y = pop(2)
            return P(binary(x, BIN[b], y))

        # ---- iteration
        if b in ('for_in_start', 'for_of_start'):
            o = pop()[0]
            self.iter_name = '__iter(%s)' % o
            return
        if b in ('for_in_next', 'for_of_next'):
            it = self.iter_name or '__iter'
            P('%s.value' % it)
            return P('%s.done' % it)

        # ---- misc
        if b in ('null',):
            return P('null')
        if b in ('undefined',):
            return P('undefined')
        if b == 'to_propkey2':
            return
        if b == 'close_loc':
            return

        # ---- fallback: keep the disassembly honest
        desc = self.d.desc(ins.op)
        npop, npush = desc[2], desc[3]
        for _ in range(min(npop or 0, len(self.st))):
            self.st.pop()
        for _ in range(npush or 0):
            P('/*%s*/' % name)
        self.anoms.append('unhandled:' + name)
        em('/* unhandled %s fmt=%s */' % (name, fmt))

    def _argc(self, ins, hint):
        if hint is not None:
            return hint
        if ins.fmt in ('npop', 'u8'):
            return self.bc[ins.pos + 1]
        if ins.fmt in ('npop_u16', 'u16'):
            return struct.unpack_from('<H', self.bc, ins.pos + 1)[0]
        if ins.fmt == 'npopx':
            return 0
        return 0


def decompile_file(jsc, ops, opts, builtins):
    """Render a whole .jsc -> dict of sections."""
    out = {'module': None, 'functions': []}
    entry = jsc.module.get('func')
    if entry:
        r = FuncRenderer(jsc, ops, entry, opts, index='entry')
        out['module'] = {'sig': r.signature(), 'lines': r.render(),
                         'anoms': r.anoms, 'exact': r.exact}
    for n, f in enumerate(jsc.functions):
        r = FuncRenderer(jsc, ops, f, opts, index=n)
        out['functions'].append({'index': n, 'name': f['name'], 'sig': r.signature(),
                                 'lines': r.render(), 'anoms': r.anoms,
                                 'exact': r.exact})
    return out
