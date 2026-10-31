"""Opcode tables, instruction decoding and structural validation."""

import re
import struct

from .tables import OPCODE_TABLES, ATOM_TABLES

# Formats that carry an absolute-or-relative jump target.
JUMP_FMTS = ('label', 'label8', 'label16', 'label_u16', 'atom_label_u8',
             'atom_label_u16')

_PREFIX_LEN = {'none': 0, 'none_int': 0, 'none_loc': 0, 'none_arg': 0,
               'none_var_ref': 0, 'nop': 0, 'u8': 1, 'i8': 1, 'loc8': 1,
               'const8': 1, 'label8': 1, 'u16': 2, 'i16': 2, 'label16': 2,
               'npop': 1, 'npopx': 0, 'npop_u16': 2, 'loc': 2, 'arg': 2,
               'var_ref': 2, 'u32': 4, 'i32': 4, 'const': 4, 'label': 4,
               'atom': 4, 'atom_u8': 5, 'atom_u16': 6, 'atom_label_u8': 9,
               'atom_label_u16': 10, 'label_u16': 6}


class Ins:
    __slots__ = ('pos', 'name', 'size', 'fmt', 'op', 'extra', 'text', 'next')

    def __init__(self, pos, name, size, fmt, op, extra, text):
        self.pos = pos
        self.name = name
        self.size = size
        self.fmt = fmt
        self.op = op
        self.extra = extra          # ('atom'|'loc'|'arg'|'varref'|'const'|'label'|'imm', value) or None
        self.text = text
        self.next = pos + size

    def __repr__(self):
        return '<%04x %s %s>' % (self.pos, self.name, self.text)


class OpTable:
    """One QuickJS opcode table (a specific upstream release)."""

    def __init__(self, version='2020-11-08'):
        if version not in OPCODE_TABLES:
            raise KeyError('unknown opcode table %r (have: %s)'
                           % (version, ', '.join(sorted(OPCODE_TABLES))))
        self.version = version
        d = OPCODE_TABLES[version]
        self.K = d['K']
        self.ops = {}
        for i, rec in enumerate(d['pre']):
            self.ops[i] = rec
        for i, rec in enumerate(d['short']):
            self.ops[self.K + i] = rec
        self.push0 = next((b for b, r in self.ops.items() if r[0] == 'push_0'), None)
        self.max_op = max(self.ops)
        self.atom_names = ATOM_TABLES[version]

    # ------------------------------------------------------------ decoding
    def operand(self, bc, pos, fmt, op):
        if fmt in ('none', 'none_loc', 'none_arg', 'none_var_ref', 'nop', 'npopx'):
            return '', None
        if fmt == 'none_int':
            v = op - self.push0 if self.push0 is not None else 0
            return str(v), ('imm', v)
        if fmt == 'u8':
            return str(bc[pos + 1]), None
        if fmt == 'i8':
            return str(struct.unpack_from('<b', bc, pos + 1)[0]), None
        if fmt == 'loc8':
            return 'r%d' % bc[pos + 1], ('loc', bc[pos + 1])
        if fmt == 'const8':
            return 'c%d' % bc[pos + 1], ('const', bc[pos + 1])
        if fmt == 'label8':
            v = struct.unpack_from('<b', bc, pos + 1)[0]
            return 'lbl:%d' % v, ('label', v)
        if fmt == 'u16':
            return str(struct.unpack_from('<H', bc, pos + 1)[0]), None
        if fmt == 'i16':
            return str(struct.unpack_from('<h', bc, pos + 1)[0]), None
        if fmt == 'label16':
            v = struct.unpack_from('<h', bc, pos + 1)[0]
            return 'lbl:%d' % v, ('label', v)
        if fmt == 'npop':
            return 'n:%d' % bc[pos + 1], ('imm', bc[pos + 1])
        if fmt == 'npop_u16':
            v = struct.unpack_from('<H', bc, pos + 1)[0]
            return 'n:%d' % v, ('imm', v)
        if fmt == 'loc':
            v = struct.unpack_from('<H', bc, pos + 1)[0]
            return 'r%d' % v, ('loc', v)
        if fmt == 'arg':
            v = struct.unpack_from('<H', bc, pos + 1)[0]
            return 'a%d' % v, ('arg', v)
        if fmt == 'var_ref':
            v = struct.unpack_from('<H', bc, pos + 1)[0]
            return 'v%d' % v, ('varref', v)
        if fmt == 'u32':
            return str(struct.unpack_from('<I', bc, pos + 1)[0]), None
        if fmt == 'i32':
            return str(struct.unpack_from('<i', bc, pos + 1)[0]), None
        if fmt == 'const':
            v = struct.unpack_from('<I', bc, pos + 1)[0]
            return 'c%d' % v, ('const', v)
        if fmt == 'label':
            v = struct.unpack_from('<I', bc, pos + 1)[0]
            return 'lbl:%d' % v, ('label', v)
        if fmt == 'atom':
            v = struct.unpack_from('<I', bc, pos + 1)[0]
            return 'atom:%d' % v, ('atom', v)
        if fmt == 'atom_u8':
            v = struct.unpack_from('<I', bc, pos + 1)[0]
            return 'atom:%d,%d' % (v, bc[pos + 5]), ('atom', v)
        if fmt == 'atom_u16':
            v = struct.unpack_from('<I', bc, pos + 1)[0]
            return 'atom:%d,%d' % (v, struct.unpack_from('<H', bc, pos + 5)[0]), ('atom', v)
        if fmt == 'atom_label_u8':
            v = struct.unpack_from('<I', bc, pos + 1)[0]
            t = struct.unpack_from('<I', bc, pos + 5)[0]
            return 'atom:%d,lbl:%d,%d' % (v, t, bc[pos + 9]), ('atom', v)
        if fmt == 'atom_label_u16':
            v = struct.unpack_from('<I', bc, pos + 1)[0]
            t = struct.unpack_from('<I', bc, pos + 5)[0]
            return 'atom:%d,lbl:%d,%d' % (v, t, struct.unpack_from('<H', bc, pos + 9)[0]), ('atom', v)
        if fmt == 'label_u16':
            t = struct.unpack_from('<I', bc, pos + 1)[0]
            return 'lbl:%d,%d' % (t, struct.unpack_from('<H', bc, pos + 5)[0]), ('label', t)
        raise ValueError('unsupported operand format %r' % fmt)

    def desc(self, op):
        return self.ops.get(op, ('<unknown>', 1, 0, 0, 'none'))

    def decode(self, bc):
        """-> (ins_list, ok, exact)"""
        ins = []
        pos = 0
        n = len(bc)
        ok = True
        while pos < n:
            op = bc[pos]
            if op not in self.ops:
                ins.append(Ins(pos, '<op%d>' % op, 1, 'none', op, None, ''))
                ok = False
                pos += 1
                continue
            name, size, npop, npush, fmt = self.ops[op]
            if pos + size > n:
                ins.append(Ins(pos, '%s<trunc>' % name, n - pos, 'none', op, None, ''))
                ok = False
                break
            text, extra = self.operand(bc, pos, fmt, op)
            ins.append(Ins(pos, name, size, fmt, op, extra, text))
            pos += size
        return ins, ok, pos == n

    # --------------------------------------------------------- normalising
    @staticmethod
    def normalize(name):
        """Collapse short/variant opcodes -> (base_name, inline_argc).

        inline_argc is the implicit operand of the get_loc0..3 / call0..3 style
        encodings that Vela emits heavily; it is None for the explicit forms.
        """
        m = re.match(r'^(call|tail_call|get_loc|put_loc|set_loc|get_arg|put_arg|'
                     r'set_arg|get_var_ref|put_var_ref|set_var_ref)([0-3])$', name)
        if m:
            return m.group(1), int(m.group(2))
        for suffix in ('8', '16'):
            if name.endswith(suffix) and name[:-len(suffix)] in (
                    'push_const', 'fclosure', 'if_true', 'if_false', 'goto',
                    'get_field', 'put_field', 'get_arg', 'put_arg', 'set_loc',
                    'put_loc', 'get_loc', 'get_var_ref', 'put_var_ref',
                    'call', 'tail_call'):
                return name[:-len(suffix)], None
        return name, None


def resolve_label(ins_list, pos, raw, fmt=None):
    """Resolve a jump operand to an instruction start.

    QuickJS stores jump targets relative to the *next* instruction; the Vela
    toolchain also emits absolute targets for the u32 forms.  The 8/16-bit
    forms are always relative, so they are tried that way first (an absolute
    value can coincidentally land on an instruction boundary).
    """
    starts = {i.pos for i in ins_list}
    t = raw & 0xFFFFFFFF
    sg = t - (1 << 32) if t >= (1 << 31) else t
    if fmt in ('label8', 'label16'):
        cands = (pos + 1 + sg, pos + sg, t)
    else:
        cands = (t, pos + 1 + sg, pos + sg)
    for c in cands:
        if c in starts:
            return c
    return None


def validate(jsc, ops):
    """Structural sanity checks that do not depend on the decompiler.

    Returns a dict with per-category violation counts; an opcode table that is
    the wrong vintage for the file shows up here immediately.
    """
    out = {'files': 1, 'functions': 0, 'instructions': 0, 'not_exact': 0,
           'unknown_opcode': 0, 'bad_jump': 0, 'bad_atom': 0, 'bad_pool': 0,
           'bad_slot': 0}
    for f in jsc.functions:
        out['functions'] += 1
        ins, ok, exact = ops.decode(f['bytecode'])
        out['instructions'] += len(ins)
        if not exact:
            out['not_exact'] += 1
        starts = {i.pos for i in ins}
        ncp = f['cpool_count']
        nloc = f['var_count'] + f['arg_count']
        for i in ins:
            if i.name.startswith('<op') or i.name.endswith('<trunc>'):
                out['unknown_opcode'] += 1
                continue
            if i.fmt in JUMP_FMTS:
                t = resolve_label(ins, i.pos, i.extra[1], i.fmt)
                if t is None:
                    out['bad_jump'] += 1
            if i.fmt == 'const' and i.extra and i.extra[1] >= ncp:
                out['bad_pool'] += 1
            if i.fmt == 'const8' and i.extra and i.extra[1] >= ncp:
                out['bad_pool'] += 1
            if i.extra and i.extra[0] == 'atom':
                k = i.extra[1] & 0x7fffffff
                if k >= jsc.atom_base and k - jsc.atom_base >= len(jsc.atoms):
                    out['bad_atom'] += 1
            if i.extra and i.extra[0] in ('loc', 'arg') and i.extra[1] >= max(nloc, 1):
                out['bad_slot'] += 1
    out['penalty'] = (out['unknown_opcode'] + out['bad_jump'] + out['bad_atom']
                      + out['bad_pool'] + out['bad_slot'])
    return out


def autodetect(jsc, versions=None):
    """Pick the opcode table that best explains the file."""
    versions = versions or list(OPCODE_TABLES)
    best = None
    for v in versions:
        r = validate(jsc, OpTable(v))
        if best is None or r['penalty'] < best[1]['penalty']:
            best = (v, r)
    return best


def score_key(r):
    return (r['penalty'], r['not_exact'])
