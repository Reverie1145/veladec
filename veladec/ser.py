"""QuickJS bytecode container reader (.jsc).

Mirrors qjsc's serialization (quickjs.c: JS_WriteObject / JS_WriteObjectAtoms /
JS_WriteFunctionBytecode), including the Vela/aiot variants observed in
watch-app (rpk) bundles:

  * atom table entries      : leb128 v; len = v>>1; wide = v&1; payload latin1 or UTF-16LE
  * bytecode atom operands  : raw u32 = predefined_id (<ATOM_BASE) or ATOM_BASE + table_index
  * jump labels             : absolute u32 OR relative to (pc+1) -- both are seen in the wild
"""

import struct

TAGS = {
    1: 'null', 2: 'undefined', 3: 'false', 4: 'true', 5: 'int', 6: 'float',
    7: 'string', 8: 'object', 9: 'array', 10: 'bigint', 11: 'bigfloat',
    12: 'bigdecimal', 13: 'template', 14: 'function', 15: 'module',
    16: 'typedarray', 17: 'arraybuffer', 18: 'sharedarraybuffer', 19: 'date',
    20: 'object_value', 21: 'object_reference',
}

ATOM_BASE_DEFAULT = 212


class Reader:
    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def u16(self):
        v = struct.unpack_from('<H', self.d, self.p)[0]
        self.p += 2
        return v

    def u32(self):
        v = struct.unpack_from('<I', self.d, self.p)[0]
        self.p += 4
        return v

    def take(self, n):
        v = self.d[self.p:self.p + n]
        self.p += n
        return v

    def leb(self):
        r = 0
        sh = 0
        while True:
            b = self.u8()
            r |= (b & 0x7f) << sh
            sh += 7
            if not b & 0x80:
                return r

    def sleb(self):
        r = 0
        sh = 0
        while True:
            b = self.u8()
            r |= (b & 0x7f) << sh
            sh += 7
            if not b & 0x80:
                if b & 0x40:
                    r -= (1 << sh)
                return r

    def atom_ref(self):
        """bc_put_atom: (index<<1) or ((small_int<<1)|1)."""
        v = self.leb()
        if v & 1:
            return ('#int', v >> 1)
        return v >> 1

    def string(self):
        v = self.leb()
        n, wide = v >> 1, v & 1
        raw = self.take(n * 2 if wide else n)
        return raw.decode('utf-16-le' if wide else 'latin1', 'replace')


class JscFile:
    """Parsed .jsc container."""

    def __init__(self, data, atom_base=ATOM_BASE_DEFAULT, builtin_names=None):
        self.data = data
        self.atom_base = atom_base
        self.builtin = builtin_names or {}
        self.atoms = []
        self.functions = []
        r = Reader(data)
        self.bc_version = r.u8()
        for _ in range(r.leb()):
            self.atoms.append(r.string())
        self.atoms_end = r.p
        self.module = self._object(r, 0)
        self.end = r.p
        self.trailing = len(data) - r.p

    # ---------------------------------------------------------------- atoms
    def atom(self, k, builtin_fallback=True):
        """Resolve a decoded atom operand to a name.

        k is either a plain int (predefined id if < atom_base, else table index
        + atom_base), a ('#int', n) tuple, or -- for bytecode operands -- an int
        that may carry the 0x80000000 flag seen on Vela field atoms.
        """
        if isinstance(k, tuple):
            return str(k[1])
        if k is None:
            return '<null>'
        k &= 0x7fffffff
        if k < self.atom_base:
            if k == 0:
                return '<null>'
            nm = self.builtin.get(k)
            return nm if nm else ('$k%d' % k if not builtin_fallback else '$k%d' % k)
        i = k - self.atom_base
        if 0 <= i < len(self.atoms):
            return self.atoms[i]
        return '<bad atom %d>' % i

    def atom_is_builtin(self, k):
        return isinstance(k, int) and (k & 0x7fffffff) < self.atom_base

    # ------------------------------------------------------------- objects
    def _object(self, r, depth):
        tag = r.u8()
        kind = TAGS.get(tag, 'tag%d' % tag)
        if kind == 'module':
            return self._module(r, depth)
        if kind == 'function':
            return self._function(r, depth)
        if kind == 'string':
            return r.string()
        if kind == 'int':
            return r.sleb()
        if kind == 'float':
            return struct.unpack('<d', r.take(8))[0]
        if kind == 'null':
            return None
        if kind == 'undefined':
            return ('undefined',)
        if kind == 'true':
            return True
        if kind == 'false':
            return False
        raise ValueError('unsupported object tag %d at 0x%x' % (tag, r.p - 1))

    def _module(self, r, depth):
        m = {'kind': 'module', 'offset': r.p}
        m['name'] = self.atom(r.atom_ref())
        m['requires'] = [self.atom(r.atom_ref()) for _ in range(r.leb())]
        exports = []
        for _ in range(r.leb()):
            t = r.u8()
            if t == 0:
                exports.append(('local', r.leb(), self.atom(r.atom_ref())))
            else:
                exports.append(('indirect', r.leb(), self.atom(r.atom_ref()),
                                self.atom(r.atom_ref())))
        m['exports'] = exports
        m['star_exports'] = [r.leb() for _ in range(r.leb())]
        imports = []
        for _ in range(r.leb()):
            var_idx = r.leb()
            name = self.atom(r.atom_ref())
            req = r.leb()
            imports.append((var_idx, name, req))
        m['imports'] = imports
        m['func'] = self._object(r, depth + 1)
        return m

    def _function(self, r, depth):
        f = {'kind': 'function', 'offset': r.p - 1, 'depth': depth}
        f['flags'] = r.u16()
        f['has_debug'] = bool((f['flags'] >> 10) & 1)
        f['js_mode'] = r.u8()
        f['name'] = self.atom(r.atom_ref())
        for k in ('arg_count', 'var_count', 'defined_arg_count', 'stack_size',
                  'closure_var_count', 'cpool_count', 'byte_code_len'):
            f[k] = r.leb()
        vardefs = []
        for _ in range(r.leb()):
            vardefs.append({'name': self.atom(r.atom_ref()),
                            'scope_level': r.leb(),
                            'scope_next': r.leb() - 1,
                            'flags': r.u8()})
        f['vardefs'] = vardefs
        closure = []
        for _ in range(f['closure_var_count']):
            closure.append({'name': self.atom(r.atom_ref()),
                            'var_idx': r.leb(), 'flags': r.u8()})
        f['closure_vars'] = closure
        f['bytecode'] = r.take(f['byte_code_len'])
        if f['has_debug']:
            f['filename'] = self.atom(r.atom_ref())
            f['line_num'] = r.leb()
            f['pc2line'] = r.take(r.leb())
        pool = []
        for _ in range(f['cpool_count']):
            pool.append(self._object(r, depth + 1))
        f['cpool'] = pool
        self.functions.append(f)
        return f

    # ------------------------------------------------------------- helpers
    def walk(self):
        """Yield every function object in pre-order, module entry first."""
        seen = []
        stack = [self.module.get('func')]
        while stack:
            f = stack.pop(0)
            if not f:
                continue
            seen.append(f)
            for c in f.get('cpool', []):
                if isinstance(c, dict) and c.get('kind') == 'function':
                    stack.append(c)
        return seen
