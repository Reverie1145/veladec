"""Instruction listing: decoded ops -> assembly lines."""

from ..decomp import jsstr
from ..ins import resolve_label, JUMP_FMTS


def asm_lines(jsc, ops, f, show_atoms=True):
    ins, ok, exact = ops.decode(f['bytecode'])
    out = []
    for i in ins:
        txt = ''
        if i.extra and i.extra[0] == 'atom' and show_atoms:
            txt = '  ; %s' % jsc.atom(i.extra[1])
        elif i.fmt in JUMP_FMTS:
            t = resolve_label(ins, i.pos, i.extra[1], i.fmt)
            txt = '  ; -> %s' % ('L%04x' % t if t is not None else 'unresolved')
        elif i.fmt == 'const' and i.extra:
            v = f['cpool'][i.extra[1]] if i.extra[1] < len(f['cpool']) else None
            txt = '  ; %s' % (('<fn:%s>' % (v.get('name') or 'anon'))
                              if isinstance(v, dict) else jsstr(v))
        out.append('%04x  %-18s %-14s%s' % (i.pos, i.name, i.text, txt))
    out.append('%s  ; exact=%s len=%d' % ('.' * 8, exact, len(f['bytecode'])))
    return out


def render_lines(lines):
    return '\n'.join(('    ' * l.depth) + l.text for l in lines)
