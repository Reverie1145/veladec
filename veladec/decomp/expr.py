"""Expression formatting: JS literals, precedence, and stack-value rendering."""

import re


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
