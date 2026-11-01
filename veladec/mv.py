"""mv -- module / view map: entry, view-model literal, closures, xrefs.

Answers the questions a bytecode reader actually asks, on one screen:

  * which function is the module entry, and what does it export
  * which function builds the page / VM object literal, and which of its fields
    are `data` constants vs. methods (with the `fn[N]` for each method)
  * per function: arity, locals, closures, cpool size, bytecode size
  * where each captured closure variable really binds (parent fn + slot + name)
  * which functions each function creates (`fclosure`), and which fields /
    methods it touches (`get_field` / `put_field` / `get_field2;call_method`)

The map is deliberately shallow: an index, not a decompilation.  Every row
points at an `fn[N]`, so `disasm --fn N` stays the final authority.
"""

import json

_PUSH_OPS = frozenset((
    'push_i32', 'push_i16', 'push_const', 'push_atom_value', 'push_empty_string',
    'push_true', 'push_false', 'push_null', 'push_undefined', 'push_minus_one',
    'push_0', 'push_1', 'push_2', 'push_3', 'push_4', 'push_5', 'push_6', 'push_7',
))

_LIFECYCLE = frozenset(('onInit', 'onReady', 'onShow', 'onHide', 'onDestroy',
                        'onBackPress', 'onMenuPress', 'onRefresh', 'onPageHide',
                        'onConfigurationChanged', 'onResize'))

_FIELD_PUT = frozenset(('put_field', 'put_field2', 'define_field'))
_FIELD_GET = frozenset(('get_field', 'get_field2'))


# ------------------------------------------------------------------ helpers
def _atom_of(ins, jsc):
    if ins.extra and ins.extra[0] == 'atom':
        return jsc.atom(ins.extra[1])
    return None


def _named(v):
    return v if v not in (None, '<null>', '') else '?'


def _brief(v, limit=30):
    """Short, unambiguous rendering of a constant-pool entry."""
    if isinstance(v, dict):
        k = v.get('kind')
        if k == 'function':
            return '<fn>'
        if k == 'module':
            return '<module>'
        return '<%s>' % k
    if isinstance(v, tuple):
        return 'undefined'
    if isinstance(v, str):
        s = json.dumps(v, ensure_ascii=False)
        return s if len(s) <= limit else s[:limit - 3] + '..."'
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float):
        return repr(v)
    return str(v)


def _const_of(ins, fn):
    """Value of a `push_const` / `push_i32` operand, resolved via the cpool."""
    if ins.extra and ins.extra[0] == 'const':
        n = ins.extra[1]
        if 0 <= n < len(fn['cpool']):
            return fn['cpool'][n]
        return '<cpool %d?>' % n
    if ins.extra and ins.extra[0] == 'imm':
        return ins.extra[1]
    if ins.name.startswith('push_') and ins.text:
        t = ins.text.lstrip('-')
        if t.isdigit():
            return int(ins.text)
    return None


class Map:
    """Structural map of one .jsc file."""

    def __init__(self, rel, jsc, ops):
        self.rel = rel
        self.jsc = jsc
        self.ops = ops
        self.fns = jsc.functions
        self.idx = {id(f): i for i, f in enumerate(self.fns)}
        self.entry = jsc.module.get('func')
        self.parent = self._parents()
        self.info = [self._scan(f) for f in self.fns]
        self.literals = [self._literal(f) for f in self.fns]
        self.builders = self._builders()
        self.made_by = {}
        for i, inf in enumerate(self.info):
            for t in inf['creates']:
                self.made_by.setdefault(t, []).append(i)
        self.names = self._name_index()

    # -------------------------------------------------------------- structure
    def _parents(self):
        par = {}
        stack = [(self.entry, None)] if self.entry else []
        while stack:
            f, p = stack.pop()
            if not f or id(f) in par:
                continue
            par[id(f)] = p
            for c in f.get('cpool', ()):
                if isinstance(c, dict) and c.get('kind') == 'function':
                    stack.append((c, f))
        for f in self.fns:                       # orphans (rare, but be safe)
            par.setdefault(id(f), None)
        return par

    def _scan(self, fn):
        try:
            ins, ok, exact = self.ops.decode(fn['bytecode'])
        except Exception:                        # a bad table must not kill the map
            ins, ok, exact = [], False, False
        creates, reads, writes, calls = [], [], [], []
        last_atom = None
        for it in ins:
            nm = self.ops.normalize(it.name)[0]
            if nm == 'fclosure':
                if it.extra and it.extra[0] == 'const':
                    n = it.extra[1]
                    if 0 <= n < len(fn['cpool']):
                        v = fn['cpool'][n]
                        if isinstance(v, dict) and v.get('kind') == 'function':
                            creates.append(self.idx.get(id(v), -1))
            elif nm in _FIELD_PUT:
                a = _atom_of(it, self.jsc)
                if a is not None:
                    writes.append(a)
            elif nm in _FIELD_GET:
                a = _atom_of(it, self.jsc)
                if a is not None:
                    reads.append(a)
                    last_atom = a
            elif nm == 'call_method':
                if last_atom:
                    calls.append(last_atom)
                    last_atom = None
        return {'ins': ins, 'exact': exact, 'creates': creates,
                'reads': reads, 'writes': writes, 'calls': calls}

    def _literal(self, fn):
        """Fields of the outermost object literal built by `fn`.

        QuickJS keeps the literal object on the stack and only pops the value
        (`define_field`), so tracking `object` ... `define_field` pairs is
        exact and does not pick up unrelated `put_field` assignments.
        """
        out = []
        i = self.idx.get(id(fn))
        if i is None:
            return out
        in_lit = False
        pend = None
        for it in self.info[i]['ins']:
            nm = self.ops.normalize(it.name)[0]
            if nm == 'object':
                in_lit, pend = True, None
                continue
            if not in_lit:
                continue
            if nm == 'fclosure':
                pend = ('fn', it.extra[1] if it.extra else None)
            elif nm in _PUSH_OPS:
                pend = ('val', _brief(_const_of(it, fn)))
            elif nm == 'object':
                pend = ('obj', None)
            elif nm == 'define_field':
                a = _atom_of(it, self.jsc)
                if a is not None and not a.startswith('$k'):
                    rec = (a, pend[0] if pend else '?', pend[1] if pend else None)
                    if rec not in out:
                        out.append(rec)
                pend = None
            elif nm in ('put_field', 'put_field2', 'call', 'call_method', 'call0',
                        'call1', 'call2', 'call3', 'put_loc', 'set_loc', 'drop',
                        'return', 'array_from', 'define_array_el'):
                in_lit, pend = False, None
        return out

    def _builders(self, top=3):
        """Functions that build an interesting object literal, best first."""
        scored = []
        for i, lit in enumerate(self.literals):
            names = {n for n, _, _ in lit}
            meth = sum(1 for _, k, _ in lit if k == 'fn')
            consts = len(lit) - meth
            if not lit:
                continue
            score = 2 * meth + len(lit)
            if names & _LIFECYCLE:
                score += 1000
            if 'data' in names:
                score += 400
            scored.append((score, meth, consts, len(lit), i))
        scored.sort(reverse=True)
        return [x[4] for x in scored[:top]]

    def _name_index(self):
        """name -> {'w': {fn}, 'r': {fn}} for every field/atom touch."""
        idx = {}
        for i, inf in enumerate(self.info):
            for n in inf['writes']:
                idx.setdefault(n, {'w': set(), 'r': set()})['w'].add(i)
            for n in tuple(inf['reads']) + tuple(inf['calls']):
                idx.setdefault(n, {'w': set(), 'r': set()})['r'].add(i)
        return {k: v for k, v in idx.items() if not k.startswith('$k')}

    def name_rows(self, grep=None, limit=40):
        rows = []
        for name in sorted(self.names):
            if grep and grep.lower() not in name.lower():
                continue
            w, r = sorted(self.names[name]['w']), sorted(self.names[name]['r'])
            rows.append((len(w) + len(r), name, w, r))
        if grep:
            rows.sort(key=lambda x: (x[1]))
            return rows[:200], max(0, len(rows) - 200)
        rows.sort(key=lambda x: (x[0], x[1]))
        return rows[:limit], max(0, len(rows) - limit)

    # ------------------------------------------------------------- closures
    def bind(self, fn, i):
        """Where closure variable i of fn comes from: (fn_index, kind, slot)."""
        cur, curf = fn['closure_vars'][i], fn
        for _ in range(8):                       # a capture chain is never deep
            p = self.parent.get(id(curf))
            if p is None:
                return (-1, 'top', cur['var_idx'])
            flags = cur['flags']
            # QuickJS js_closure(): is_local -> parent var slot, is_arg -> parent
            # argument, else -> parent closure-var slot (lexical / var capture).
            if flags & 1:
                return (self.idx.get(id(p), -1), 'r', cur['var_idx'])
            if flags & 2:
                return (self.idx.get(id(p), -1), 'a', cur['var_idx'])
            n = cur['var_idx']
            if n < len(p['closure_vars']):
                cur, curf = p['closure_vars'][n], p
                continue
            return (self.idx.get(id(p), -1), '?', n)
        return (-1, '?', cur['var_idx'])

    def var_name(self, fn, kind, slot):
        vd = fn.get('vardefs') or []
        if kind in ('r', 'a') and slot < len(vd):
            return _named(vd[slot]['name'])
        return None

    def binding(self, fn, i):
        """(declared name, 'fn[N].r<slot> (name)') for closure variable i."""
        cv = fn['closure_vars'][i]
        pidx, kind, slot = self.bind(fn, i)
        if pidx < 0:
            loc = '<top>'
        else:
            loc = 'fn[%d].%s%d' % (pidx, kind, slot)
            vn = self.var_name(self.fns[pidx], kind, slot)
            if vn and vn != '?':
                loc += ' (%s)' % vn
        return _named(cv['name']), loc

    def binding_line(self, fn, i):
        nm, loc = self.binding(fn, i)
        return '%s <- %s' % (nm, loc)

    # ------------------------------------------------------------------ stats
    def totals(self):
        return (len(self.fns),
                sum(len(i['ins']) for i in self.info),
                sum(1 for i in self.info if not i['exact']))


# ------------------------------------------------------------------ rendering
def _sig(m, i):
    f = m.fns[i]
    return 'a%-2d v%-2d cl%-2d cp%-3d %5di' % (
        f['arg_count'], f['var_count'], f['closure_var_count'],
        f['cpool_count'], len(m.info[i]['ins']))


def _fn_row(m, i):
    return 'fn[%3d] %-22s %s%s' % (i, _named(m.fns[i].get('name'))[:22],
                                   _sig(m, i), '' if m.info[i]['exact'] else ' !')


def _detail(m, i):
    f = m.fns[i]
    out = ['', '=' * 74, _fn_row(m, i), '=' * 74,
           'offset 0x%x  block %d B  stack %d  arg %d  var %d  closure %d  cpool %d'
           % (f['offset'], f['byte_code_len'], f['stack_size'],
              f['arg_count'], f['var_count'], f['closure_var_count'],
              f['cpool_count'])]
    if f.get('has_debug'):
        out.append('debug   %s:%d' % (f.get('filename'), f.get('line_num', 0)))
    made_by = sorted(set(m.made_by.get(i, ())))
    out.append('made by %s' % (', '.join('fn[%d]' % x for x in made_by) or '-'))
    vd = f.get('vardefs') or []
    if vd:
        out.append('vars    ' + ', '.join('r%d=%s' % (k, _named(v['name']))
                                          for k, v in enumerate(vd)))
    if f['closure_vars']:
        out.append('closures:')
        for k, cv in enumerate(f['closure_vars']):
            fl = '+'.join(t for b, t in ((1, 'local'), (2, 'arg'), (4, 'const'),
                                         (8, 'lexical'), (16, 'var'))
                          if cv['flags'] & b) or '0'
            out.append('  v%d  %-20s idx=%-3d fl=0x%x (%-14s) %s' % (
                k, _named(cv['name']), cv['var_idx'], cv['flags'], fl,
                m.binding_line(f, k)))
    if f['cpool']:
        out.append('cpool:')
        for k, v in enumerate(f['cpool']):
            if isinstance(v, dict) and v.get('kind') == 'function':
                t = m.idx.get(id(v), -1)
                out.append('  c%-3d fn[%d] %s %s' % (k, t, _named(v.get('name'))[:20],
                                                     _sig(m, t)))
            else:
                out.append('  c%-3d %s' % (k, _brief(v, 60)))
    inf = m.info[i]
    for lab, key in (('writes', 'writes'), ('reads', 'reads'),
                     ('calls ', 'calls'), ('makes ', 'creates')):
        vals = sorted(set(inf[key]))
        if vals:
            if key == 'creates':
                out.append('%s %s' % (lab, ', '.join('fn[%d]' % x for x in vals)))
            else:
                out.append('%s %s' % (lab, ', '.join(vals)))
    return out


def _literal_block(m, label, lit, fn_i=None):
    meth = [x for x in lit if x[1] == 'fn']
    data = [x for x in lit if x[1] != 'fn']
    out = [label]
    if meth:
        out.append('  methods:')
        for name, _, cn in meth:
            tgt = -1
            src = m.entry if fn_i is None else m.fns[fn_i]
            if isinstance(cn, int) and 0 <= cn < len(src['cpool']):
                v = src['cpool'][cn]
                if isinstance(v, dict) and v.get('kind') == 'function':
                    tgt = m.idx.get(id(v), -1)
            out.append('    %-26s fn[%d]' % (name, tgt))
    if data:
        out.append('  fields:')
        for name, kind, val in data[:24]:
            out.append('    %-26s = %s' % (name, val if kind == 'val' else '<%s>' % kind))
        if len(data) > 24:
            out.append('    ... +%d more' % (len(data) - 24))
    return out


def render_text(maps, header, grep=None, limit=40):
    out = list(header)
    for m in maps:
        nfn, nins, nbad = m.totals()
        out += ['', '#' * 74,
                '# %s   %d fns / %d insns%s' % (
                    m.rel, nfn, nins, '' if not nbad else '  (%d undecoded)' % nbad),
                '#' * 74]
        mod = m.jsc.module
        if mod.get('name') not in (None, '<null>', ''):
            out.append('module   %s' % mod['name'])
        if mod.get('requires'):
            out.append('requires %s' % ', '.join(mod['requires']))
        if mod.get('imports'):
            out.append('imports  ' + ', '.join('%s#%d' % (n, r)
                                               for _, n, r in mod['imports']))
        if mod.get('exports'):
            out.append('exports  ' + ', '.join(_named(e[-1]) for e in mod['exports']))
        if m.entry:
            ei = m.idx.get(id(m.entry), -1)
            out.append('entry    fn[%d] %s %s' % (
                ei, _named(m.entry.get('name'))[:20], _sig(m, ei)))
        for rank, fi in enumerate(m.builders):
            lit = m.literals[fi]
            meth_n = sum(1 for _, k, _ in lit if k == 'fn')
            names = {n for n, _, _ in lit}
            tag = ('view literal' if (names & _LIFECYCLE or 'data' in names)
                   else 'literal')
            out += _literal_block(m, '%-13s fn[%d] %s  (%d fields, %d methods)'
                                  % (tag + ':', fi, _named(m.fns[fi].get('name'))[:18],
                                     len(lit), meth_n), lit, fi)
        rows, more = m.name_rows(grep, limit)
        if rows:
            out.append('')
            out.append('name index   (w = field written, r = read / method called)')
            for _, name, w, r in rows:
                out.append('  %-28s %s%s' % (
                    name[:28],
                    ('w:' + ','.join('fn[%d]' % x for x in w[:6])
                     + ('+%d' % (len(w) - 6) if len(w) > 6 else '')) if w else '',
                    ('  r:' + ','.join('fn[%d]' % x for x in r[:6])
                     + ('+%d' % (len(r) - 6) if len(r) > 6 else '')) if r else ''))
            if more:
                out.append('  ... +%d more (use --grep)' % more)
        out.append('')
        out.append('%-8s %-22s %-25s %s' % ('id', 'name', 'arg var clos cpool size',
                                            'xref'))
        for i in range(nfn):
            tail = []
            if m.fns[i]['closure_vars']:
                tail.append('clos: ' + '; '.join(
                    m.binding_line(m.fns[i], k)
                    for k in range(min(3, len(m.fns[i]['closure_vars'])))))
            inf = m.info[i]
            if inf['calls']:
                tail.append('calls: ' + ','.join(sorted(set(inf['calls']))[:5]))
            if inf['creates']:
                tail.append('makes: ' + ','.join('fn[%d]' % x
                                                 for x in sorted(set(inf['creates']))[:5]))
            out.append(_fn_row(m, i) + ('  ' + '  '.join(tail) if tail else ''))
    return '\n'.join(out) + '\n'


def render_json(maps, header):
    doc = {'tool': 'veladec mv', 'files': []}
    for m in maps:
        nfn, nins, nbad = m.totals()
        doc['files'].append({
            'file': m.rel, 'functions': nfn, 'insns': nins, 'undecoded': nbad,
            'module': {k: m.jsc.module.get(k) for k in ('name', 'requires', 'exports')},
            'entry': m.idx.get(id(m.entry), -1) if m.entry else -1,
            'builders': [{'fn': fi, 'fields': len(m.literals[fi]),
                          'methods': [{'name': n, 'fn': None} for n, k, _ in
                                      m.literals[fi] if k == 'fn'],
                          'data': [{'name': n, 'value': v}
                                   for n, k, v in m.literals[fi] if k != 'fn']}
                         for fi in m.builders],
            'names': {n: {'w': sorted(v['w']), 'r': sorted(v['r'])}
                      for n, v in sorted(m.names.items())},
            'fns': [{
                'id': i, 'name': m.fns[i].get('name'),
                'arg': m.fns[i]['arg_count'], 'var': m.fns[i]['var_count'],
                'insns': len(m.info[i]['ins']), 'exact': m.info[i]['exact'],
                'vars': [v['name'] for v in (m.fns[i].get('vardefs') or [])],
                'closures': [{'name': cv['name'], 'var_idx': cv['var_idx'],
                              'flags': cv['flags'],
                              'binds': dict(zip(('name', 'loc'), m.binding(m.fns[i], k)))}
                             for k, cv in enumerate(m.fns[i]['closure_vars'])],
                'cpool': [_brief(v, 80) for v in m.fns[i]['cpool']],
                'writes': sorted(set(m.info[i]['writes'])),
                'reads': sorted(set(m.info[i]['reads'])),
                'calls': sorted(set(m.info[i]['calls'])),
                'creates': sorted(set(m.info[i]['creates'])),
                'made_by': sorted(set(m.made_by.get(i, ()))),
            } for i in range(nfn)],
        })
    return json.dumps(doc, ensure_ascii=False, indent=1) + '\n'


def render_md(maps, header, grep=None, limit=40):
    return '# %s\n\n```\n%s\n```\n' % (
        header[0].lstrip('# ').strip(),
        render_text(maps, header, grep, limit).rstrip())
