"""Opcode dispatch: turns one decoded instruction into emitted pseudo-JS."""

import re
import struct

from .expr import (BIN, UN, UN_SWAP, binary, call_expr, jsstr, negate,


                   render_val)


class DispatchMixin:
    """The per-opcode translation table, mixed into FuncRenderer."""

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
