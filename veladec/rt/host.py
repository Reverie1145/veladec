"""Host objects and property access for the veladec runtime.

`Host` owns the global scope and the stub implementations of the platform
APIs a quick-app handler touches (console, storage, device, router, ...).
Every stubbed call is recorded, so a trace can show what the program asked
the platform for even though nothing real is attached.
"""

import json
import math

from .values import (U, NAN, INF, Cell, HostFn, JSFunction, JsRegex, JsError,
                     Permissive,
                     is_num, is_nan, to_num, to_str, to_int32, truthy,
                     eq_loose, eq_strict, cmp_lt, parse_int, parse_float,
                     fmt_num)


class Recorder(object):
    """Ordered log of platform calls made by the bytecode under test."""

    def __init__(self, limit=2000):
        self.rows = []
        self.limit = limit

    def add(self, name, args, result=U, note=''):
        if len(self.rows) < self.limit:
            self.rows.append({'api': name, 'args': list(args),
                              'result': result, 'note': note})
        return result

    def __len__(self):
        return len(self.rows)

    def to_json(self):
        from .values import to_plain
        return [{'api': r['api'],
                 'args': [to_plain(a) for a in r['args']],
                 'result': to_plain(r['result']),
                 'note': r['note']} for r in self.rows]


class _LCG(object):
    """Deterministic Math.random so two runs of the same command agree."""

    def __init__(self, seed=0x2F6E2B1):
        self.s = seed & 0xFFFFFFFF

    def next(self):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s / float(0x7FFFFFFF)


class Host(object):
    def __init__(self, storage=None, device_id='VELADEC-DEVICE-0001',
                 now=1700000000000, globals_extra=None, rng_seed=0x2F6E2B1):
        self.rec = Recorder()
        self.storage = dict(storage or {})
        self.device_id = device_id
        self.now = int(now)
        self.extra = dict(globals_extra or {})
        self.rng = _LCG(rng_seed)
        self.globals = self._build_globals()

    # ------------------------------------------------------------- globals
    def _build_globals(self):
        g = {
            'undefined': U,
            'NaN': NAN,
            'Infinity': INF,
            'globalThis': None,
            'parseInt': HostFn('parseInt', lambda v, r=10: parse_int(v, r)),
            'parseFloat': HostFn('parseFloat', parse_float),
            'isNaN': HostFn('isNaN', lambda v: is_nan(to_num(v))),
            'isFinite': HostFn('isFinite', lambda v: not (is_nan(to_num(v))
                                                         or abs(to_num(v)) == INF)),
            'String': self._str_ctor(),
            'Number': HostFn('Number', lambda v=0: to_num(v)),
            'Boolean': HostFn('Boolean', lambda v=U: truthy(v)),
            'Math': self._math(),
            'JSON': self._json(),
            'Object': self._object_ctor(),
            'Array': self._array_ctor(),
            'Date': self._date(),
            'RegExp': HostFn('RegExp', lambda p, f='': JsRegex(p, f)),
            'Error': HostFn('Error', lambda m='': JsError('Error', to_str(m))),
            'console': self._console(),
            'storage': self._storage_api(),
            'device': self._device_api(),
            'router': self._router_api(),
            'vibrator': {'vibrate': HostFn('vibrator.vibrate',
                                           lambda o=U: self.rec.add('vibrator.vibrate', [o], True))},
            'showToast': HostFn('showToast', self._toast),
            'require': HostFn('require', self._require),
        }
        g['globalThis'] = g
        g.update(self.extra)
        return g

    # ------------------------------------------------------------- recorders
    def _toast(self, msg=U, dur=U):
        self.rec.add('showToast', [msg, dur], U, note='toast')
        return U

    def _console(self):
        def mk(level):
            def call(*a):
                self.rec.add('console.' + level, list(a), U, note='log')
                return U
            return HostFn('console.' + level, call)
        return {k: mk(k) for k in ('log', 'warn', 'error', 'info', 'debug')}

    def _storage_api(self):
        def get(key=U, success=U, fail=U):
            k = key.get('key') if isinstance(key, dict) else key
            if isinstance(key, dict):
                success = key.get('success', success)
                fail = key.get('fail', fail)
            ks = to_str(k)
            val = self.storage.get(ks, U)
            self.rec.add('storage.get', [ks], val, note='hit' if ks in self.storage else 'miss')
            self._cb(success, val)
            return val

        def setv(arg=U, success=U, fail=U):
            d = arg if isinstance(arg, dict) else {'key': arg}
            if isinstance(arg, dict) and 'success' in arg:
                success = arg.get('success')
            k = to_str(d.get('key', U))
            v = d.get('value', d.get('state', U))
            self.storage[k] = v
            self.rec.add('storage.set', [k, v], U, note='store')
            self._cb(success)
            return U

        def delete(key=U, success=U):
            ks = to_str(key.get('key') if isinstance(key, dict) else key)
            self.storage.pop(ks, None)
            self.rec.add('storage.delete', [ks], U)
            return U

        return {'get': HostFn('storage.get', get),
                'set': HostFn('storage.set', setv),
                'delete': HostFn('storage.delete', delete),
                'clear': HostFn('storage.clear',
                                lambda: (self.storage.clear(),
                                         self.rec.add('storage.clear', [], U))[1])}

    def _device_api(self):
        def dev_id(arg=U):
            succ = arg.get('success') if isinstance(arg, dict) else U
            val = {'deviceId': self.device_id, 'brand': 'veladec',
                   'model': 'vm', 'serial': self.device_id}
            self.rec.add('device.getDeviceId', [], val, note='stub')
            self._cb(succ, val)
            return val

        def info(arg=U):
            succ = arg.get('success') if isinstance(arg, dict) else U
            val = {'brand': 'veladec', 'model': 'vm', 'serial': self.device_id}
            self.rec.add('device.getInfo', [], val, note='stub')
            self._cb(succ, val)
            return val

        return {'getDeviceId': HostFn('device.getDeviceId', dev_id),
                'getInfo': HostFn('device.getInfo', info),
                'getSerial': HostFn('device.getSerial', dev_id)}

    def _router_api(self):
        def r(name):
            def call(arg=U):
                self.rec.add('router.' + name, [arg], U, note='nav')
                return U
            return HostFn('router.' + name, call)
        return {k: r(k) for k in ('push', 'replace', 'back', 'clear')}

    # ---------------------------------------------------------------- Math
    def _math(self):
        m = {
            'abs': lambda x: abs(to_num(x)),
            'floor': lambda x: float(math.floor(to_num(x))) if not (is_nan(to_num(x)) or abs(to_num(x)) == INF) else to_num(x),
            'ceil': lambda x: float(math.ceil(to_num(x))) if not (is_nan(to_num(x)) or abs(to_num(x)) == INF) else to_num(x),
            'round': lambda x: float(math.floor(to_num(x) + 0.5)),
            'trunc': lambda x: float(math.trunc(to_num(x))),
            'sign': lambda x: (0 if to_num(x) == 0 else (1 if to_num(x) > 0 else -1)),
            'sqrt': lambda x: math.sqrt(to_num(x)) if to_num(x) >= 0 else NAN,
            'cbrt': lambda x: math.copysign(abs(to_num(x)) ** (1.0 / 3), to_num(x)),
            'pow': lambda a, b: _safe(lambda: math.pow(to_num(a), to_num(b))),
            'exp': lambda x: _safe(lambda: math.exp(to_num(x))),
            'log': lambda x: _safe(lambda: math.log(to_num(x))),
            'log2': lambda x: _safe(lambda: math.log2(to_num(x))),
            'log10': lambda x: _safe(lambda: math.log10(to_num(x))),
            'sin': lambda x: _safe(lambda: math.sin(to_num(x))),
            'cos': lambda x: _safe(lambda: math.cos(to_num(x))),
            'tan': lambda x: _safe(lambda: math.tan(to_num(x))),
            'atan': lambda x: _safe(lambda: math.atan(to_num(x))),
            'atan2': lambda y, x: _safe(lambda: math.atan2(to_num(y), to_num(x))),
            'asin': lambda x: _safe(lambda: math.asin(to_num(x))),
            'acos': lambda x: _safe(lambda: math.acos(to_num(x))),
            'min': lambda *a: min([to_num(x) for x in a]) if a else INF,
            'max': lambda *a: max([to_num(x) for x in a]) if a else -INF,
            'random': lambda: self.rng.next(),
            'imul': lambda a, b: to_int32((to_int32(a) * to_int32(b)) & 0xFFFFFFFF),
            'hypot': lambda *a: math.sqrt(sum(to_num(x) ** 2 for x in a)),
            'PI': math.pi, 'E': math.e,
            'LN2': math.log(2), 'LN10': math.log(10),
            'SQRT2': math.sqrt(2), 'SQRT1_2': math.sqrt(0.5),
        }
        return {k: (HostFn('Math.' + k, v) if callable(v) else v)
                for k, v in m.items()}

    # ---------------------------------------------------------------- JSON
    def _json(self):
        def stringify(v, indent=U):
            spaces = None
            if is_num(indent):
                spaces = int(to_num(indent))
            elif isinstance(indent, str):
                spaces = indent
            return json.dumps(_py(v), ensure_ascii=False,
                              indent=spaces, separators=(',', ':') if spaces is None else None)

        def parse(s):
            try:
                from .values import from_plain
                return from_plain(json.loads(to_str(s)))
            except Exception as e:
                raise _Throw(JsError('SyntaxError', str(e)))

        return {'stringify': HostFn('JSON.stringify', stringify),
                'parse': HostFn('JSON.parse', parse)}

    # -------------------------------------------------------------- Object
    def _str_ctor(self):
        ctor = HostFn('String', lambda v=U: to_str(v))
        ctor.props = {
            'fromCharCode': HostFn('String.fromCharCode',
                                   lambda *a: ''.join(chr(to_int32(x) & 0xffff)
                                                      for x in a)),
            'fromCodePoint': HostFn('String.fromCodePoint',
                                    lambda *a: ''.join(chr(int(to_num(x)))
                                                       for x in a)),
            'raw': HostFn('String.raw', lambda o, *a: to_str(o)),
        }
        return ctor

    def _object_ctor(self):
        def assign(t, *srcs):
            if isinstance(t, dict):
                for s in srcs:
                    if isinstance(s, dict):
                        t.update(s)
            return t

        def define_property(o, k, desc):
            if isinstance(o, dict) and isinstance(desc, dict) and 'value' in desc:
                o[to_str(k)] = desc['value']
            return o

        def create(proto, props=U):
            d = {}
            if isinstance(props, dict):
                for k, v in props.items():
                    d[to_str(k)] = v.get('value', U) if isinstance(v, dict) else v
            return d

        ctor = HostFn('Object', lambda v=U: v if isinstance(v, dict) else {})
        ctor.props = {
            'assign': HostFn('Object.assign', assign),
            'keys': HostFn('Object.keys', lambda o: list(o.keys()) if isinstance(o, dict) else []),
            'values': HostFn('Object.values', lambda o: list(o.values()) if isinstance(o, dict) else []),
            'entries': HostFn('Object.entries', lambda o: [[k, v] for k, v in o.items()] if isinstance(o, dict) else []),
            'freeze': HostFn('Object.freeze', lambda o: o),
            'isFrozen': HostFn('Object.isFrozen', lambda o: True),
            'defineProperty': HostFn('Object.defineProperty', define_property),
            'defineProperties': HostFn('Object.defineProperties', lambda o, p: o),
            'create': HostFn('Object.create', create),
            'getPrototypeOf': HostFn('Object.getPrototypeOf', lambda o: U),
            'seal': HostFn('Object.seal', lambda o: o),
            'fromEntries': HostFn('Object.fromEntries',
                                  lambda it: {to_str(k): v for k, v in it}),
        }
        return ctor

    # --------------------------------------------------------------- Array
    def _array_ctor(self):
        def mk(*a):
            if len(a) == 1 and is_num(a[0]):
                return [U] * int(to_num(a[0]))
            return list(a)

        ctor = HostFn('Array', mk)
        ctor.props = {
            'isArray': HostFn('Array.isArray', lambda v: isinstance(v, list)),
            'from': HostFn('Array.from', lambda v, f=U: _array_from(self, v, f)),
            'of': HostFn('Array.of', lambda *a: list(a)),
        }
        return ctor

    # ---------------------------------------------------------------- Date
    def _date(self):
        ctor = HostFn('Date', lambda *a: {'$date': self.now if not a else to_num(a[0])})
        ctor.props = {'now': HostFn('Date.now', lambda: self.now)}
        return ctor

    def _cb(self, fn, *args):
        """Call a JS callback (success/fail) the way the engine would."""
        if not isinstance(fn, (JSFunction, HostFn)):
            return U
        rt = getattr(self, 'rt', None)
        if rt is not None and isinstance(fn, JSFunction):
            return rt.call(fn, list(args), U)
        return fn(*args)

    # ------------------------------------------------------------ property
    SYSTEM_MODULES = ('storage', 'device', 'vibrator', 'router', 'fetch',
                      'app', 'crypto', 'file')

    def _require(self, name=U):
        mod_name = to_str(name)
        leaf = mod_name.rsplit('.', 1)[-1]
        if mod_name.startswith('@app-module/system.') and leaf in self.SYSTEM_MODULES:
            impl = self.globals.get(leaf)
            if impl is not None:
                mod = {'__esModule': True, 'default': impl, 'moduleName': mod_name}
                self.rec.add('require', [name], '<system module %s>' % leaf)
                return mod
        mod = Permissive(mod_name)
        self.rec.add('require', [name], '<module %s>' % mod.name)
        return mod

    def getprop(self, obj, key, rt=None):
        k = key if isinstance(key, str) else to_str(key)
        if isinstance(obj, Permissive):
            if k in obj:
                return obj[k]
            self.rec.add('%s.%s' % (obj.name, k), [], '<stub>', note='module')
            return HostFn('%s.%s' % (obj.name, k), lambda *a: U)
        if isinstance(obj, dict) and '$date' in obj:
            return _date_method(obj, k)
        if isinstance(obj, dict):
            if k in obj:
                return obj[k]
            return _DICT_METHODS.get(k, lambda o, *a: U).__get__(obj, dict) \
                if k in _NOARG_KEYS else U
        if isinstance(obj, list):
            if k == 'length':
                return len(obj)
            if is_num(key) or k.lstrip('-').isdigit():
                i = int(to_num(key))
                return obj[i] if -len(obj) <= i < len(obj) else U
            return _array_method(self, rt, obj, k)
        if isinstance(obj, str):
            if k == 'length':
                return len(obj)
            if k.lstrip('-').isdigit():
                i = int(key)
                return obj[i] if 0 <= i < len(obj) else U
            return _string_method(self, rt, obj, k)
        if is_num(obj):
            return _number_method(obj, k)
        if isinstance(obj, bool):
            return _number_method(int(obj), k) if k in ('toString', 'valueOf') else U
        if isinstance(obj, (JSFunction, HostFn)):
            if k == 'length':
                fd = getattr(obj, 'fd', None)
                return fd.get('arg_count', 0) if fd else 0
            if k == 'name':
                return getattr(obj, 'name', '') or ''
            if k in ('call', 'apply') and rt is not None:
                def call(this=U, *a):
                    return rt.call(obj, list(a), this)
                def apply(this=U, arr=U):
                    return rt.call(obj, list(arr) if isinstance(arr, list) else [], this)
                return HostFn(k, call if k == 'call' else apply)
            return getattr(obj, 'props', {}).get(k, U)
        if isinstance(obj, JsRegex):
            if k == 'test' and rt is not None:
                return HostFn('RegExp.test',
                              lambda s: bool(obj.rx.search(to_str(s))) if obj.rx else False)
            if k == 'source':
                return obj.src
            if k == 'global':
                return 'g' in str(obj.flags)
            return U
        if isinstance(obj, JsError):
            return {'name': obj.name, 'message': obj.message}.get(k, U)
        return U

    def setprop(self, obj, key, val):
        if isinstance(obj, list):
            if is_num(key) or (isinstance(key, str) and key.lstrip('-').isdigit()):
                i = int(to_num(key))
                while len(obj) <= i:
                    obj.append(U)
                if i >= 0:
                    obj[i] = val
                return
            if key == 'length':
                n = int(to_num(val))
                del obj[n:]
                while len(obj) < n:
                    obj.append(U)
                return
        if isinstance(obj, dict):
            obj[to_str(key)] = val


class _Throw(Exception):
    def __init__(self, value):
        self.value = value
        Exception.__init__(self, repr(value))


def _safe(f):
    try:
        return f()
    except (ValueError, OverflowError):
        return NAN


def _py(v):
    if v is U or v is None:
        return None
    if isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return None if v != v else v
    if isinstance(v, list):
        return [_py(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _py(x) for k, x in v.items()}
    if isinstance(v, (JSFunction, HostFn)):
        return None
    return to_str(v)


def _array_from(host, v, f=U):
    src = v if isinstance(v, list) else (list(v) if hasattr(v, '__iter__') and not isinstance(v, (str, dict)) else to_str(v))
    out = list(src)
    return out


_DICT_METHODS = {
    'toString': lambda o: '[object Object]',
    'valueOf': lambda o: o,
    'hasOwnProperty': lambda o, k: to_str(k) in o,
}

_NOARG_KEYS = ('toString', 'valueOf', 'hasOwnProperty')


def _number_method(n, k):
    if k == 'toString':
        def ts(radix=10):
            r = int(to_num(radix))
            if r == 10:
                return fmt_num(n)
            v = int(to_num(n))
            neg = v < 0
            v = abs(v)
            al = '0123456789abcdefghijklmnopqrstuvwxyz'
            if v == 0:
                return '0'
            out = ''
            while v:
                out = al[v % r] + out
                v //= r
            return ('-' if neg else '') + out
        return HostFn('Number.toString', ts)
    if k == 'toFixed':
        return HostFn('Number.toFixed', lambda d=0: '%.*f' % (int(to_num(d)), to_num(n)))
    if k == 'toPrecision':
        return HostFn('Number.toPrecision', lambda p=0: fmt_num(n))
    if k == 'valueOf':
        return HostFn('Number.valueOf', lambda: n)
    return U



def _date_method(obj, k):
    import datetime as _dt
    t = obj['$date']
    d = _dt.datetime.fromtimestamp(t / 1000.0)
    table = {
        'getTime': lambda: t,
        'valueOf': lambda: t,
        'getFullYear': lambda: d.year,
        'getMonth': lambda: d.month - 1,
        'getDate': lambda: d.day,
        'getDay': lambda: d.isoweekday() % 7,
        'getHours': lambda: d.hour,
        'getMinutes': lambda: d.minute,
        'getSeconds': lambda: d.second,
        'getMilliseconds': lambda: int(t) % 1000,
        'toISOString': lambda: d.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (int(t) % 1000),
        'toJSON': lambda: d.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (int(t) % 1000),
        'toString': lambda: d.strftime('%a %b %d %Y %H:%M:%S'),
        'toLocaleString': lambda: d.strftime('%Y/%m/%d %H:%M:%S'),
        'toLocaleDateString': lambda: d.strftime('%Y/%m/%d'),
        'toLocaleTimeString': lambda: d.strftime('%H:%M:%S'),
    }
    fn = table.get(k)
    return HostFn('Date.' + k, fn) if fn else U


def _string_method(host, rt, s, k):
    def idx(v, default=0):
        n = int(to_num(v))
        return n if not is_nan(to_num(v)) else default

    table = {
        'charAt': lambda i=0: s[idx(i)] if 0 <= idx(i) < len(s) else '',
        'charCodeAt': lambda i=0: ord(s[idx(i)]) if 0 <= idx(i) < len(s) else NAN,
        'codePointAt': lambda i=0: ord(s[idx(i)]) if 0 <= idx(i) < len(s) else U,
        'indexOf': lambda sub, start=0: s.find(to_str(sub), idx(start)),
        'lastIndexOf': lambda sub, start=U: s.rfind(to_str(sub)) if start is U else s.rfind(to_str(sub), 0, idx(start) + 1),
        'includes': lambda sub, start=0: to_str(sub) in s[idx(start):],
        'startsWith': lambda sub, start=0: s.startswith(to_str(sub), idx(start)),
        'endsWith': lambda sub, end=U: s.endswith(to_str(sub)) if end is U else s.endswith(to_str(sub), 0, idx(end)),
        'slice': lambda a=0, b=U: s[idx(a):None if b is U else idx(b)],
        'substring': lambda a=0, b=U: s[max(0, idx(a)):None if b is U else max(0, idx(b))],
        'substr': lambda a=0, b=U: s[idx(a):None if b is U else idx(a) + idx(b)],
        'toUpperCase': lambda: s.upper(),
        'toLowerCase': lambda: s.lower(),
        'trim': lambda: s.strip(),
        'trimStart': lambda: s.lstrip(),
        'trimEnd': lambda: s.rstrip(),
        'split': lambda sep=U, lim=U: _split(s, sep, lim),
        'repeat': lambda n=0: s * max(0, int(to_num(n))),
        'padStart': lambda n=0, c=' ': s.rjust(int(to_num(n)), to_str(c)[:1] or ' '),
        'padEnd': lambda n=0, c=' ': s.ljust(int(to_num(n)), to_str(c)[:1] or ' '),
        'concat': lambda *a: s + ''.join(to_str(x) for x in a),
        'toString': lambda: s,
        'valueOf': lambda: s,
        'replace': lambda a, b: _replace(rt, s, a, b, False),
        'replaceAll': lambda a, b: _replace(rt, s, a, b, True),
        'match': lambda re: _match(s, re),
        'search': lambda re: (re.rx.search(s).start() if isinstance(re, JsRegex) and re.rx and re.rx.search(s) else -1),
    }
    fn = table.get(k)
    if fn is None:
        return U
    return HostFn('String.' + k, fn)


def _split(s, sep, lim):
    if sep is U:
        out = [s]
    elif isinstance(sep, JsRegex):
        out = sep.rx.split(s) if sep.rx else [s]
    else:
        sp = to_str(sep)
        out = list(s) if sp == '' else s.split(sp)
    if is_num(lim):
        out = out[:int(to_num(lim))]
    return out


def _replace(rt, s, a, b, all_):
    import re
    if isinstance(a, JsRegex):
        pat = a.rx if a.rx else None
        if pat is None:
            return s
        def repl(m):
            if isinstance(b, (JSFunction, HostFn)):
                return to_str(rt.call(b, [m.group(0)] + list(m.groups()), U))
            return to_str(b).replace('$&', m.group(0))
        return pat.sub(repl, s, count=0 if all_ or 'g' in str(a.flags) else 1)
    needle = to_str(a)
    if needle == '':
        return s
    if isinstance(b, (JSFunction, HostFn)):
        def repl2(m):
            return to_str(rt.call(b, [m.group(0), m.start(), s], U))
        return re.sub(re.escape(needle), repl2, s, count=0 if all_ else 1)
    return s.replace(needle, to_str(b), -1 if all_ else 1)


def _match(s, re_):
    if not isinstance(re_, JsRegex) or not re_.rx:
        return None
    if 'g' in str(re_.flags):
        return re_.rx.findall(s)
    m = re_.rx.search(s)
    return [m.group(0)] + list(m.groups()) if m else None


def _array_method(host, rt, arr, k):
    def slice_(a=0, b=U):
        return arr[int(to_num(a)):None if b is U else int(to_num(b))]

    table = {
        'push': lambda *a: (arr.extend(list(a)), len(arr))[1],
        'pop': lambda: arr.pop() if arr else U,
        'shift': lambda: arr.pop(0) if arr else U,
        'unshift': lambda *a: (arr.__setitem__(slice(0, 0), list(a)), len(arr))[1],
        'indexOf': lambda x, start=0: _index_of(arr, x, start),
        'lastIndexOf': lambda x: (len(arr) - 1 - arr[::-1].index(x)) if x in arr else -1,
        'includes': lambda x: x in arr,
        'join': lambda sep=',': to_str(sep).join('' if x is U or x is None else to_str(x) for x in arr),
        'concat': lambda *a: arr + [y for x in a for y in (x if isinstance(x, list) else [x])],
        'slice': slice_,
        'splice': lambda a=0, b=U, *items: _splice(arr, a, b, items),
        'reverse': lambda: (arr.reverse(), arr)[1],
        'sort': lambda f=U: _sort(rt, arr, f),
        'map': lambda f: [rt.call(f, [x, i, arr]) for i, x in enumerate(arr)],
        'filter': lambda f: [x for i, x in enumerate(arr) if truthy(rt.call(f, [x, i, arr]))],
        'forEach': lambda f: [rt.call(f, [x, i, arr]) for i, x in enumerate(arr)] and U,
        'find': lambda f: next((x for i, x in enumerate(arr) if truthy(rt.call(f, [x, i, arr]))), U),
        'findIndex': lambda f: next((i for i, x in enumerate(arr) if truthy(rt.call(f, [x, i, arr]))), -1),
        'some': lambda f: any(truthy(rt.call(f, [x, i, arr])) for i, x in enumerate(arr)),
        'every': lambda f: all(truthy(rt.call(f, [x, i, arr])) for i, x in enumerate(arr)),
        'reduce': lambda f, init=U: _reduce(rt, arr, f, init),
        'fill': lambda v, a=0, b=U: _fill(arr, v, a, b),
        'flat': lambda d=1: _flat(arr, int(to_num(d))),
        'toString': lambda: ','.join(to_str(x) for x in arr),
        'keys': lambda: list(range(len(arr))),
        'entries': lambda: [[i, x] for i, x in enumerate(arr)],
    }
    fn = table.get(k)
    return HostFn('Array.' + k, fn) if fn else U


def _index_of(arr, x, start=0):
    st = int(to_num(start)) if is_num(start) else 0
    for i in range(max(0, st), len(arr)):
        if arr[i] is x or eq_strict(arr[i], x):
            return i
    return -1


def _splice(arr, a, b, items):
    i = int(to_num(a))
    if i < 0:
        i = max(0, len(arr) + i)
    n = len(arr) - i if b is U else int(to_num(b))
    removed = arr[i:i + n]
    arr[i:i + n] = list(items)
    return removed


def _sort(rt, arr, f):
    if not isinstance(f, (JSFunction, HostFn)):
        arr.sort(key=lambda x: to_str(x) if not is_num(x) else to_num(x))
        return arr
    import functools

    def cmp(x, y):
        r = to_num(rt.call(f, [x, y]))
        return -1 if r < 0 else (1 if r > 0 else 0)
    arr.sort(key=functools.cmp_to_key(cmp))
    return arr


def _reduce(rt, arr, f, init):
    if init is U:
        if not arr:
            raise _Throw(JsError('TypeError', 'reduce of empty array with no initial value'))
        acc = arr[0]
        rest = arr[1:]
    else:
        acc = init
        rest = arr
    for i, x in enumerate(rest):
        acc = rt.call(f, [acc, x, i, arr])
    return acc


def _fill(arr, v, a, b):
    i = int(to_num(a))
    j = len(arr) if b is U else int(to_num(b))
    for k in range(max(0, i), min(len(arr), j)):
        arr[k] = v
    return arr


def _flat(arr, d):
    out = []
    for x in arr:
        if isinstance(x, list) and d > 0:
            out.extend(_flat(x, d - 1))
        else:
            out.append(x)
    return out
