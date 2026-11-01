"""FuncRenderer: drives the linear stack-expression recovery pass."""

from .dispatch import DispatchMixin
from .expr import jsstr, negate, render_val
from .structure import Line, StructureMixin


class FuncRenderer(StructureMixin, DispatchMixin):
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
