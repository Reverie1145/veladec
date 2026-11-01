"""Bytecode interpreter: the dynamic half of veladec.

Given a decoded function, execute it against a `Host` and report what happened
-- return value, every call with arguments, every field access you asked to
watch, and every platform API the program tried to reach.

This is not a JS engine. It runs one function (or a chain of them) the way the
device would, so that a value you only ever saw as arithmetic in an `asm`
listing can be printed, step by step, with its inputs.
"""

import math

from ..builtins import BUILTINS
from .host import Host, _Throw
from .atoms import (candidates as atom_candidates, learn as atom_learn,
                    alts as atom_alts)
from .values import (U, NAN, INF, Cell, JSFunction, HostFn, JsRegex, JsError,
                     is_num, is_nan, to_num, to_str, to_int32, to_uint32,
                     truthy, eq_loose, eq_strict, cmp_lt, typeof, to_plain)

STEP_LIMIT = 5000000


class UnsupportedOpcode(Exception):
    def __init__(self, name, fn_index, pos, text=''):
        self.name, self.fn_index, self.pos, self.text = name, fn_index, pos, text
        Exception.__init__(self, 'unsupported opcode %s at fn[%s]:0x%04x %s'
                           % (name, fn_index, pos, text))


class VarRef(object):
    """A cell over (container, index) so parent and child frames share state."""

    __slots__ = ('c', 'i')

    def __init__(self, container, index):
        self.c = container
        self.i = index

    @property
    def v(self):
        try:
            return self.c[self.i]
        except Exception:
            return U

    @v.setter
    def v(self, val):
        self.c[self.i] = val


class Frame(object):
    __slots__ = ('fd', 'loc', 'arg', 'refs', 'st', 'index', 'pos', 'depth',
                 'handlers', 'gosub')

    def __init__(self, fd, arg, refs, index, depth):
        self.fd = fd
        self.arg = arg
        self.loc = [U] * fd['var_count']
        self.refs = refs
        self.st = []
        self.index = index
        self.pos = 0
        self.depth = depth


class Interp(object):
    def __init__(self, jsc, ops, host=None, max_steps=STEP_LIMIT, trace=False,
                 trace_calls=False, watch=(), stop_at=None, call_limit=5000,
                 sink=None, watch_calls=(), atoms=None, fill='undefined',
                 snaps=()):
        self.jsc = jsc
        self.ops = ops
        self.host = host or Host()
        self.host.rt = self
        self.max_steps = max_steps
        self.trace = trace
        self.trace_calls = trace_calls
        self.watch = {w.lower() for w in watch}
        self.watch_calls = {int(w) for w in watch_calls}
        self.stop_at = dict(stop_at or {})
        self.call_limit = call_limit
        self.sink = sink if sink is not None else (lambda s: print(s))
        self.calls = []
        self.events = []
        self.steps = 0
        self.depth = 0
        self.stopped = 'return'
        self.closure_count = 0
        self._dec = {}
        self._atom = dict(BUILTINS)
        self._atom_override = {int(k): v for k, v in (atoms or {}).items()}
        self._atom.update(self._atom_override)
        self.atom_notes = []
        self.capture = True
        self.hits = {}
        self.snaps = list(snaps)
        self.snapshots = []
        self.frames_kept = {}
        self.fill = fill
        self.fill_value = {'undefined': U, 'require': self.host.globals['require'],
                           'noop': HostFn('noop', lambda *a: U)}.get(fill, U)

    # ------------------------------------------------------------- helpers
    def atom(self, k):
        if k & 0x80000000:
            # QuickJS tagged-int atom: the id *is* the small integer, and it is
            # used as a property name ('0'..'n') — never as a builtin.
            return str(k & 0x7fffffff)
        kk = k & 0x7fffffff
        base = getattr(self.jsc, 'atom_base', 212)
        if kk < base:
            return self._atom.get(kk, '$k%d' % kk)
        atoms = self.jsc.atoms
        return atoms[kk - base] if kk - base < len(atoms) else '$k%d' % kk

    def _load_atoms(self, names):
        if names:
            self._atom.update({int(k): v for k, v in names.items()})

    def decode(self, fd):
        key = id(fd)
        d = self._dec.get(key)
        if d is None:
            ins, ok, exact = self.ops.decode(fd['bytecode'])
            by = {i.pos: i for i in ins}
            d = (ins, by, {i.pos for i in ins})
            self._dec[key] = d
        return d

    def _emit(self, line):
        self.sink(line)

    def _watch_hit(self, kind, name, obj, val, f):
        ev = {'kind': kind, 'name': name, 'fn': f.index,
              'pos': f.pos, 'value': val,
              'obj': type(obj).__name__ if not isinstance(obj, dict) else 'object'}
        self.events.append(ev)
        self._emit('   %s %s <- %s   (fn[%s]:0x%04x)'
                   % (kind, name, _short(val), f.index, f.pos))

    # ---------------------------------------------------------------- call
    def call(self, fn, args, this=U, from_pos=None, from_fn=None):
        if isinstance(fn, JSFunction):
            idx = fn.index
            if idx in self.watch_calls or self.trace_calls:
                self._emit('%s-> fn[%s] %s(%s)'
                           % ('  ' * self.depth, idx,
                              fn.name or '?', ', '.join(_short(a) for a in args)))
            if len(self.calls) < self.call_limit:
                self.calls.append({'fn': idx, 'name': fn.name, 'args': args,
                                   'depth': self.depth, 'from': from_fn,
                                   'pos': from_pos})
            self.depth += 1
            try:
                r = self.exec_frame(fn.fd, args, this, fn.refs, idx)
            finally:
                self.depth -= 1
            if self.calls and self.calls[-1]['fn'] == idx and 'result' not in self.calls[-1]:
                self.calls[-1]['result'] = r
            if idx in self.watch_calls:
                self._emit('%s<- fn[%s] = %s' % ('  ' * self.depth, idx, _short(r)))
            return r
        if isinstance(fn, HostFn):
            return fn(*args)
        if callable(fn):
            return fn(*args)
        raise _Throw(JsError('TypeError', '%s is not a function' % to_str(fn)))

    def _atom_id(self, key):
        if isinstance(key, str) and key.startswith('$k'):
            try:
                return int(key[2:])
            except ValueError:
                return None
        return None

    def getprop(self, obj, key):
        aid = self._atom_id(key)
        if aid is not None:
            for cand in atom_candidates(aid, self._atom_override.get(aid)):
                v = self.host.getprop(obj, cand, self)
                if v is not U:
                    atom_learn(aid, cand)
                    if self._atom.get(aid) != cand:
                        self._atom[aid] = cand
                        self.atom_notes.append((aid, cand, getattr(self, 'fn_now', None), getattr(self, 'pos_now', 0)))
                    return v
        v = self.host.getprop(obj, key, self)
        if v is U and isinstance(key, str):
            for alt in atom_alts(key):
                w = self.host.getprop(obj, alt, self)
                if w is not U:
                    self.atom_notes.append((key, alt, getattr(self, 'fn_now', None),
                                            getattr(self, 'pos_now', 0)))
                    return w
        return v

    def setprop(self, obj, key, val):
        return self.host.setprop(obj, key, val)

    # ---------------------------------------------------------------- exec
    def exec_frame(self, fd, args, this=U, refs=None, index=None):
        f = Frame(fd, list(args) + [self.fill_value] *
                  max(0, fd['arg_count'] - len(args)),
                  refs or [], index, self.depth)
        f.handlers = []
        f.gosub = []
        if self.capture and index is not None:
            self.frames_kept[index] = f
        while True:
            try:
                return self._run(f, this, index)
            except _LongJump as e:
                f.pos = e.target
            except _Throw as e:
                self._unwind(f, e.value)

    def _run(self, f, this, index):
        fd = f.fd
        ins, by, starts = self.decode(fd)
        cp = fd['cpool']
        handlers = f.handlers
        gosub = f.gosub
        st = f.st
        refs = f.refs
        loc, arg = f.loc, f.arg
        stops = self.stop_at.get(index, self.stop_at.get(None))
        pc = f.pos
        n = len(fd['bytecode'])

        while pc < n:
            i = by.get(pc)
            if i is None:
                pc += 1
                continue
            if self.snaps:
                for si, (sfn, sp, sn) in enumerate(self.snaps):
                    if sp == pc and (sfn is None or sfn == index):
                        key = ('s', si, pc)
                        c = self.hits.get(key, 0) + 1
                        self.hits[key] = c
                        if c == sn:
                            self.snapshots.append({
                                'fn': index, 'pos': pc,
                                'loc': list(f.loc), 'arg': list(f.arg),
                                'refs': [getattr(r, 'v', r) for r in f.refs]})
            if stops is not None and pc == stops[1] and (stops[0] is None or stops[0] == index):
                n = self.hits.get(pc, 0) + 1
                self.hits[pc] = n
                if n >= stops[2]:
                    self.stopped = 'break'
                    self.brk = f
                    return U
            self.steps += 1
            if self.steps > self.max_steps:
                self.stopped = 'limit'
                self.brk = f
                return U
            nm, inline = self.ops.normalize(i.name)
            ex = i.extra
            f.pos = pc
            self.fn_now = index
            self.pos_now = pc
            if self.trace:
                self._emit('%s%04x %-20s %-12s st=%s'
                           % ('  ' * f.depth, i.pos, i.name, i.text,
                              [_short(x) for x in st[-4:]]))
            nxt = i.next

            if nm in _PUSH_INT:
                st.append(_PUSH_INT[nm] if nm in _PUSH_INT and _PUSH_INT[nm] is not None
                          else int(i.text))
            elif nm == 'push':
                st.append(int(i.text))
            elif nm == 'push_const':
                st.append(cp[ex[1]])
            elif nm == 'push_atom_value':
                st.append(self.atom(ex[1]))
            elif nm == 'push_empty_string':
                st.append('')
            elif nm == 'push_true':
                st.append(True)
            elif nm == 'push_false':
                st.append(False)
            elif nm in ('push_null', 'null'):
                st.append(None)
            elif nm in ('push_undefined', 'undefined'):
                st.append(U)
            elif nm == 'push_this':
                st.append(this)
            elif nm == 'push_minus1':
                st.append(-1)
            # --------------------------------------------------- variables
            elif nm in ('get_loc', 'get_loc_check'):
                st.append(loc[self._k(inline, ex)])
            elif nm in ('put_loc', 'put_loc_check'):
                loc[self._k(inline, ex)] = st.pop()
            elif nm in ('set_loc', 'set_loc_uninitialized', 'set_loc_check'):
                loc[self._k(inline, ex)] = U
            elif nm == 'get_arg':
                st.append(arg[self._k(inline, ex)])
            elif nm in ('put_arg', 'set_arg'):
                arg[self._k(inline, ex)] = st.pop()
            elif nm in ('get_var_ref', 'get_var_ref_check'):
                k = self._k(inline, ex)
                st.append(refs[k].v if isinstance(refs[k], VarRef) else refs[k])
            elif nm in ('put_var_ref', 'put_var_ref_check', 'set_var_ref',
                        'set_var_ref_check'):
                k = self._k(inline, ex)
                val = st.pop() if nm.startswith('put') or not st else st[-1]
                if isinstance(refs[k], VarRef):
                    refs[k].v = val
                else:
                    refs[k] = val
            elif nm == 'get_var':
                name = self.atom(ex[1])
                st.append(self.host.globals.get(name, U))
            elif nm == 'put_var':
                name = self.atom(ex[1])
                self.host.globals[name] = st.pop()
            elif nm == 'check_define_var' or nm == 'define_var' or nm == 'check_define_var':
                pass
            # ------------------------------------------------------ fields
            elif nm == 'get_field':
                o = st.pop()
                k = self.atom(ex[1])
                v = self.getprop(o, k)
                if self.watch and k.lower() in self.watch:
                    self._watch_hit('get', k, o, v, f)
                st.append(v)
            elif nm == 'get_field2':
                o = st[-1]
                k = self.atom(ex[1])
                v = self.getprop(o, k)
                if self.watch and k.lower() in self.watch:
                    self._watch_hit('get', k, o, v, f)
                st.append(v)
            elif nm == 'put_field':
                v = st.pop()
                o = st.pop()
                k = self.atom(ex[1])
                if self.watch and k.lower() in self.watch:
                    self._watch_hit('put', k, o, v, f)
                self.setprop(o, k, v)
            elif nm == 'put_field_opt_chain' or nm == 'get_field_opt_chain':
                pass
            elif nm == 'get_array_el':
                k = st.pop()
                o = st.pop()
                st.append(self.getprop(o, k))
            elif nm == 'get_array_el2':
                k = st.pop()
                st.append(self.getprop(st[-1], k))
            elif nm == 'put_array_el':
                v = st.pop()
                k = st.pop()
                o = st.pop()
                self.setprop(o, k, v)
            elif nm == 'get_length':
                o = st.pop()
                st.append(self.getprop(o, 'length'))
            elif nm == 'to_propkey2' or nm == 'to_propkey':
                pass
            elif nm == 'to_object':
                pass
            # --------------------------------------------------- literals
            elif nm == 'object':
                st.append({})
            elif nm == 'define_field':
                v = st.pop()
                o = st.pop()
                if isinstance(o, list):
                    k = self.atom(ex[1]) if ex else to_str(v)
                    if k.isdigit():
                        i = int(k)
                        while len(o) <= i:
                            o.append(U)
                        o[i] = v
                    else:
                        o.append(v)
                elif isinstance(o, dict):
                    k = self.atom(ex[1])
                    aid = self._atom_id(ex[1] if isinstance(ex[1], str) else '$k%d' % (ex[1] & 0x7fffffff))
                    if aid is not None and atom_candidates(aid):
                        k = atom_candidates(aid)[0]
                        self._atom.setdefault(aid, k)
                    o[k] = v
                st.append(o)
            elif nm in ('define_method', 'define_method_computed'):
                v = st.pop()
                o = st.pop()
                if isinstance(o, dict):
                    k = self.atom(ex[1]) if ex else to_str(st.pop())
                    o[k] = v
                st.append(o)
            elif nm == 'append':
                v = st.pop()
                a = st[-1]
                if isinstance(a, list):
                    a.append(v)
            elif nm == 'array_from':
                cnt = ex[1] if ex else 0
                items = [st.pop() for _ in range(cnt)][::-1]
                st.append(items)
            elif nm == 'define_array_el':
                v = st.pop()
                a = st[-1]
                if isinstance(a, list):
                    a.append(v)
            elif nm == 'set_array_el':
                v = st.pop()
                k = st.pop()
                o = st.pop()
                self.setprop(o, k, v)
            elif nm == 'regexp':
                fl = st.pop()
                pat = st.pop()
                st.append(JsRegex(to_str(pat), to_str(fl)))
            # ------------------------------------------------------- math
            elif nm == 'add':
                b = st.pop(); a = st.pop()
                st.append(to_str(a) + to_str(b) if isinstance(a, str) or isinstance(b, str)
                          else to_num(a) + to_num(b))
            elif nm == 'sub':
                b = to_num(st.pop()); a = to_num(st.pop()); st.append(a - b)
            elif nm == 'mul':
                b = to_num(st.pop()); a = to_num(st.pop()); st.append(a * b)
            elif nm == 'div':
                b = to_num(st.pop()); a = to_num(st.pop())
                st.append(_div(a, b))
            elif nm == 'mod':
                b = to_num(st.pop()); a = to_num(st.pop())
                st.append(_mod(a, b))
            elif nm == 'pow':
                b = to_num(st.pop()); a = to_num(st.pop())
                st.append(_safe(lambda: float(a) ** float(b)))
            elif nm == 'neg':
                st.append(-to_num(st.pop()))
            elif nm == 'plus':
                st.append(to_num(st.pop()))
            elif nm == 'inc':
                st.append(to_num(st.pop()) + 1)
            elif nm == 'dec':
                st.append(to_num(st.pop()) - 1)
            elif nm == 'post_inc':
                v = st.pop(); st.append(v); st.append(to_num(v) + 1)
            elif nm == 'post_dec':
                v = st.pop(); st.append(v); st.append(to_num(v) - 1)
            elif nm == 'and':
                b = st.pop(); a = st.pop(); st.append(to_int32(a) & to_int32(b))
            elif nm == 'or':
                b = st.pop(); a = st.pop(); st.append(to_int32(a) | to_int32(b))
            elif nm == 'xor':
                b = st.pop(); a = st.pop(); st.append(to_int32(a) ^ to_int32(b))
            elif nm == 'shl':
                b = st.pop(); a = st.pop()
                r = (to_int32(a) << (to_uint32(b) & 31)) & 0xFFFFFFFF
                st.append(r - (1 << 32) if r >= (1 << 31) else r)
            elif nm == 'shr':
                b = st.pop(); a = st.pop()
                st.append((to_uint32(a) >> (to_uint32(b) & 31)))
            elif nm == 'sar':
                b = st.pop(); a = st.pop()
                st.append(to_int32(a) >> (to_uint32(b) & 31))
            elif nm == 'not':
                st.append(~to_int32(st.pop()))
            elif nm == 'lnot':
                st.append(not truthy(st.pop()))
            elif nm == 'typeof':
                st.append(typeof(st.pop()))
            # --------------------------------------------------- compare
            elif nm == 'lt':
                b = st.pop(); a = st.pop(); st.append(cmp_lt(a, b))
            elif nm == 'lte':
                b = st.pop(); a = st.pop(); st.append(cmp_lt(a, b) or eq_loose(a, b))
            elif nm == 'gt':
                b = st.pop(); a = st.pop(); st.append(cmp_lt(b, a))
            elif nm == 'gte':
                b = st.pop(); a = st.pop(); st.append(cmp_lt(b, a) or eq_loose(a, b))
            elif nm == 'eq':
                b = st.pop(); a = st.pop(); st.append(eq_loose(a, b))
            elif nm == 'neq':
                b = st.pop(); a = st.pop(); st.append(not eq_loose(a, b))
            elif nm == 'strict_eq':
                b = st.pop(); a = st.pop(); st.append(eq_strict(a, b))
            elif nm == 'strict_neq':
                b = st.pop(); a = st.pop(); st.append(not eq_strict(a, b))
            elif nm == 'in':
                k = st.pop(); o = st.pop()
                st.append(to_str(k) in o if isinstance(o, dict) else False)
            elif nm == 'instanceof':
                st.pop(); st.pop(); st.append(False)
            # ------------------------------------------------------ stack
            elif nm == 'dup':
                st.append(st[-1])
            elif nm == 'drop':
                if st:
                    st.pop()
            elif nm == 'nip':
                a = st.pop(); st.pop(); st.append(a)
            elif nm == 'swap':
                st[-1], st[-2] = st[-2], st[-1]
            elif nm == 'insert2':
                st.insert(len(st) - 2, st.pop())
            elif nm == 'insert3':
                st.insert(len(st) - 3, st.pop())
            elif nm == 'insert4':
                st.insert(len(st) - 4, st.pop())
            elif nm == 'rot3l':
                st[-3], st[-2], st[-1] = st[-2], st[-1], st[-3]
            elif nm == 'rot3r':
                st[-3], st[-2], st[-1] = st[-1], st[-3], st[-2]
            # ------------------------------------------------------ calls
            elif nm in ('call0', 'call1', 'call2', 'call3'):
                argc = int(nm[-1])
                a = [st.pop() for _ in range(argc)][::-1]
                fn = st.pop()
                st.append(self.call(fn, a, U, pc, index))
            elif nm in ('call', 'tail_call'):
                cnt = inline if inline is not None else (ex[1] if ex else 0)
                a = [st.pop() for _ in range(cnt)][::-1]
                fn = st.pop()
                r = self.call(fn, a, U, pc, index)
                if nm == 'tail_call':
                    return r
                st.append(r)
            elif nm in ('call_method', 'tail_call_method'):
                cnt = inline if inline is not None else (ex[1] if ex else 0)
                a = [st.pop() for _ in range(cnt)][::-1]
                fn = st.pop()
                t = st.pop()
                r = self.call(fn, a, t, pc, index)
                if nm == 'tail_call_method':
                    return r
                st.append(r)
            elif nm in ('call_constructor', 'call_constructor_regexp'):
                cnt = inline if inline is not None else (ex[1] if ex else 0)
                a = [st.pop() for _ in range(cnt)][::-1]
                ctor = st.pop()
                st.append(self._construct(ctor, a))
            elif nm == 'apply':
                arr = st.pop(); t = st.pop(); fn = st.pop()
                st.append(self.call(fn, list(arr) if isinstance(arr, list) else [], t, pc, index))
            # ----------------------------------------------------- closure
            elif nm == 'fclosure':
                c = cp[ex[1]]
                crefs = []
                for cv in c.get('closure_vars', []):
                    vi, fl = cv['var_idx'], cv['flags']
                    if fl & 1:
                        crefs.append(VarRef(arg if (fl & 2) else loc, vi))
                    else:
                        crefs.append(refs[vi] if vi < len(refs) else VarRef([U], 0))
                self.closure_count += 1
                st.append(JSFunction(c, crefs, index=self._fn_index(c)))
            elif nm == 'set_name' or nm == 'set_name_computed':
                pass
            # ------------------------------------------------------ flow
            elif nm == 'if_false':
                v = st.pop()
                if not truthy(v):
                    pc = self._target(by, starts, pc, ex, nxt)
                    continue
            elif nm == 'if_true':
                v = st.pop()
                if truthy(v):
                    pc = self._target(by, starts, pc, ex, nxt)
                    continue
            elif nm == 'goto':
                pc = self._target(by, starts, pc, ex, nxt)
                continue
            elif nm == 'catch':
                handlers.append((len(st), self._target(by, starts, pc, ex, nxt)))
            elif nm == 'gosub':
                gosub.append(nxt)
                pc = self._target(by, starts, pc, ex, nxt)
                continue
            elif nm == 'ret':
                pc = gosub.pop() if gosub else (nxt if st and st[-1] is U else st.pop())
                if not isinstance(pc, int):
                    pc = nxt
                continue
            elif nm == 'throw':
                self._raise(st.pop(), f)
            elif nm == 'return':
                return st.pop() if st else U
            elif nm == 'return_undef':
                return U
            elif nm == 'nop' or nm == 'line_num' or nm == 'debugger':
                pass
            else:
                raise UnsupportedOpcode(i.name, index, i.pos, i.text)
            pc = nxt
        return U

    # --------------------------------------------------------------- utils
    def _construct(self, ctor, args):
        if isinstance(ctor, HostFn):
            if ctor.name == 'Array':
                return list(args)
            if ctor.name == 'Date':
                return {'$date': args[0] if args else self.host.now}
            if ctor.name == 'Object':
                return {}
            if ctor.name == 'RegExp':
                return JsRegex(*[to_str(a) for a in args])
            if ctor.name == 'Error':
                return JsError('Error', to_str(args[0]) if args else '')
            try:
                return ctor(*args)
            except Exception:
                return U
        if isinstance(ctor, JSFunction):
            return self.call(ctor, args, U)
        return U

    def _raise(self, val, f):
        """Throw inside the running frame: jump to its handler or unwind."""
        if f.handlers:
            depth, target = f.handlers.pop()
            del f.st[depth:]
            f.st.append(val)
            raise _LongJump(target)
        raise _Throw(val)

    def _unwind(self, f, val):
        """A throw crossed a frame boundary: try this frame's handlers."""
        if f.handlers:
            depth, target = f.handlers.pop()
            del f.st[depth:]
            f.st.append(val)
            f.pos = target
            return
        raise _Throw(val)

    def _target(self, by, starts, pc, ex, nxt):
        raw = ex[1] if ex else None
        if raw is None:
            return nxt
        t = raw & 0xFFFFFFFF
        sg = t - (1 << 32) if t >= (1 << 31) else t
        for cand in (pc + 1 + sg, pc + sg, t):
            if cand in starts:
                return cand
        return nxt

    def _k(self, inline, ex):
        return inline if inline is not None else (ex[1] if ex else 0)

    def _fn_index(self, fd):
        cache = getattr(self, '_fidx', None)
        if cache is None:
            cache = {id(x): i for i, x in enumerate(self.jsc.functions)}
            self._fidx = cache
        return cache.get(id(fd))


class _LongJump(Exception):
    def __init__(self, target):
        self.target = target
        Exception.__init__(self, 'jump')


_PUSH_INT = {
    'push_i8': None, 'push_i16': None, 'push_i32': None,
    'push_u8': None, 'push_u16': None, 'push_u32': None,
    'push_0': 0, 'push_1': 1, 'push_2': 2, 'push_3': 3, 'push_4': 4,
    'push_5': 5, 'push_6': 6, 'push_7': 7,
}


def _short(v):
    from .values import to_plain
    if isinstance(v, str):
        return repr(v) if len(v) <= 40 else repr(v[:37] + '...')
    if isinstance(v, list):
        return '[%d]' % len(v)
    if isinstance(v, dict):
        return '{%s}' % ','.join(list(v)[:4]) if v else '{}'
    if isinstance(v, JSFunction):
        return '<fn[%s] %s>' % (v.index, v.name or '?')
    if isinstance(v, HostFn):
        return '<host:%s>' % v.name
    return to_str(v)


def _div(a, b):
    if b == 0:
        if a == 0 or is_nan(a):
            return NAN
        return INF if a > 0 else -INF
    return a / b


def _mod(a, b):
    if b == 0 or is_nan(a) or is_nan(b):
        return NAN
    try:
        return math.fmod(a, b)
    except Exception:
        return NAN


def _safe(f):
    try:
        return f()
    except (ValueError, OverflowError, ZeroDivisionError):
        return NAN
