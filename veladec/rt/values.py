"""JS value model for the veladec runtime.

Only what Vela / quick-app bytecode actually needs: primitives, plain objects,
arrays, closures and regexes, plus the ECMA-262 coercion rules the QuickJS
compiler bakes into its opcodes (ToNumber / ToString / ToInt32 / ToUint32 and
the loose equality table).

Nothing here is a full JS engine -- there is no prototype chain. Property
lookup goes through ``host.getprop`` which knows the handful of built-in
methods (String#slice, Array#push, ...) that real handlers call.
"""

import math


class _Undefined(object):
    __slots__ = ()

    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super(_Undefined, cls).__new__(cls)
        return cls._inst

    def __repr__(self):
        return 'undefined'

    def __bool__(self):
        return False


U = _Undefined()
NAN = float('nan')
INF = float('inf')


class Cell(object):
    """A closure cell: frames share the same object, so writes are visible."""

    __slots__ = ('v',)

    def __init__(self, v=U):
        self.v = v

    def __repr__(self):
        return 'Cell(%r)' % (self.v,)


class JSFunction(object):
    """A bytecode function closed over a list of cells."""

    __slots__ = ('fd', 'refs', 'name', 'index')

    def __init__(self, fd, refs=(), name=None, index=None):
        self.fd = fd
        self.refs = list(refs)
        self.name = fd.get('name') if name is None else name
        self.index = index

    def __repr__(self):
        return '<fn:%s>' % (self.name or '?')


class HostFn(object):
    """A python callable exposed to bytecode, with a name for traces."""

    __slots__ = ('name', 'fn', 'props')

    def __init__(self, name, fn):
        self.name = name
        self.fn = fn
        self.props = {}

    def __call__(self, *a):
        return self.fn(*a)

    def __repr__(self):
        return '<host:%s>' % self.name


class Permissive(dict):
    """A stand-in module: any property read answers a stub function.

    ``require("@app-module/system.vibrator")`` returns one of these, so module
    factories keep running when the real platform module is absent.  Every
    access is recorded, so the transcript still says what the code wanted.
    """

    __slots__ = ('name',)

    def __init__(self, name):
        dict.__init__(self)
        self.name = name


class JsRegex(object):
    __slots__ = ('src', 'flags', 'rx')

    def __init__(self, src, flags=''):
        import re
        self.src = src
        self.flags = flags
        f = re.I if 'i' in str(flags) else 0
        try:
            self.rx = re.compile(str(src), f)
        except Exception:
            self.rx = None

    def __repr__(self):
        return '/%s/' % self.src


class JsError(object):
    """A thrown JS value that is not a plain object (Error instances)."""

    __slots__ = ('name', 'message')

    def __init__(self, name='Error', message=''):
        self.name = name
        self.message = message

    def __repr__(self):
        return '%s: %s' % (self.name, self.message)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_nan(v):
    return isinstance(v, float) and v != v


def to_num(v):
    if isinstance(v, bool):
        return 1 if v else 0
    if is_num(v):
        return v
    if v is U:
        return NAN
    if v is None:
        return 0
    if isinstance(v, str):
        s = v.strip()
        if s == '':
            return 0
        low = s.lower()
        if low in ('infinity', '+infinity'):
            return INF
        if low == '-infinity':
            return -INF
        if low.startswith('0x') or low.startswith('0b') or low.startswith('0o'):
            try:
                return int(s, 0)
            except Exception:
                return NAN
        try:
            return int(s)
        except Exception:
            try:
                return float(s)
            except Exception:
                return NAN
    if isinstance(v, list):
        return to_num(to_str(v))
    return NAN


def to_int32(v):
    n = to_num(v)
    if is_nan(n) or n in (INF, -INF):
        return 0
    n = int(n) & 0xFFFFFFFF
    return n - (1 << 32) if n >= (1 << 31) else n


def to_uint32(v):
    n = to_num(v)
    if is_nan(n) or n in (INF, -INF):
        return 0
    return int(n) & 0xFFFFFFFF


def fmt_num(v):
    if isinstance(v, float):
        if v != v:
            return 'NaN'
        if v == int(v) and abs(v) < 1e21:
            return str(int(v))
        r = repr(v)
        return r
    return str(v)


def to_str(v):
    if v is U:
        return 'undefined'
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if is_num(v):
        return fmt_num(v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ','.join('' if x is None or x is U else to_str(x) for x in v)
    if isinstance(v, (JSFunction, HostFn)):
        return 'function %s() { [native code] }' % (getattr(v, 'name', '') or '')
    if isinstance(v, JsRegex):
        return repr(v)
    if isinstance(v, JsError):
        return repr(v)
    if isinstance(v, dict):
        return '[object Object]'
    return str(v)


def truthy(v):
    if v is U or v is None or v is False:
        return False
    if is_num(v):
        return not (v == 0 or v != v)
    if isinstance(v, str):
        return len(v) > 0
    return True


def eq_strict(a, b):
    if is_num(a) and is_num(b):
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, (dict, list, JSFunction, HostFn, JsRegex, JsError, Cell)):
        return a is b
    return a is b or a == b


def eq_loose(a, b):
    if (a is U or a is None) and (b is U or b is None):
        return a is b
    if a is b:
        return True
    if is_num(a) and is_num(b):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if is_num(a) and isinstance(b, str):
        return a == to_num(b)
    if isinstance(a, str) and is_num(b):
        return to_num(a) == b
    if isinstance(a, bool) or isinstance(b, bool):
        return to_num(a) == to_num(b)
    return a is b


def cmp_lt(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a < b
    x, y = to_num(a), to_num(b)
    if is_nan(x) or is_nan(y):
        return False
    return x < y


def typeof(v):
    if v is U:
        return 'undefined'
    if isinstance(v, bool):
        return 'boolean'
    if is_num(v):
        return 'number'
    if isinstance(v, str):
        return 'string'
    if isinstance(v, (JSFunction, HostFn)) or callable(v):
        return 'function'
    return 'object'


def parse_int(v, radix=10):
    s = to_str(v).strip()
    sign = 1
    i = 0
    if s[:1] in '+-':
        sign = -1 if s[0] == '-' else 1
        i = 1
    r = int(to_num(radix)) if radix is not None else 10
    if r == 0:
        r = 10
    if r < 2 or r > 36:
        return NAN
    if r == 16 and s[i:i + 2].lower() == '0x':
        i += 2
    digits = ''
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
    while i < len(s) and s[i].lower() in alphabet[:r]:
        digits += s[i]
        i += 1
    if not digits:
        return NAN
    return sign * int(digits, r)


def parse_float(v):
    s = to_str(v).strip()
    out = ''
    for ch in s:
        if ch in '+-' and out == '':
            out += ch
        elif ch.isdigit() or ch == '.':
            out += ch
        elif ch in 'eE' and out and 'e' not in out.lower():
            out += ch
        else:
            break
    try:
        return float(out)
    except Exception:
        return NAN


def to_plain(v, depth=0, seen=None):
    """JS value -> JSON-serialisable python, for --json output."""
    seen = seen or set()
    if v is U:
        return None
    if isinstance(v, bool) or v is None:
        return v
    if is_num(v):
        if isinstance(v, float):
            if v != v:
                return 'NaN'
            if v in (INF, -INF):
                return 'Infinity' if v > 0 else '-Infinity'
        return v
    if isinstance(v, str):
        return v
    if isinstance(v, JSFunction):
        return {'$fn': v.name or '?', 'index': v.index}
    if isinstance(v, HostFn):
        return {'$host': v.name}
    if isinstance(v, JsRegex):
        return {'$re': v.src, 'flags': str(v.flags)}
    if isinstance(v, JsError):
        return {'$error': v.name, 'message': v.message}
    if depth > 6 or id(v) in seen:
        return '...'
    seen = seen | {id(v)}
    if isinstance(v, list):
        return [to_plain(x, depth + 1, seen) for x in v]
    if isinstance(v, dict):
        return {str(k): to_plain(x, depth + 1, seen) for k, x in v.items()}
    return to_str(v)


def from_plain(v):
    """JSON-loaded python -> JS value (None stays null, not undefined)."""
    if isinstance(v, list):
        return [from_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: from_plain(x) for k, x in v.items()}
    return v
