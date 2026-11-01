"""run: execute a function instead of reading it.

Dynamic analysis for Vela bytecode. Point it at one function, feed it the
values the device would have produced, and read the answer off the machine
rather than off the disassembly.
"""

import json
import re
import sys

from .. import __version__
from ..mv import Map
from ..rpk import Target
from ..rt import U, Host, Interp, UnsupportedOpcode, to_plain, from_plain, to_str
from ..rt.host import _Throw
from ..rt.values import JSFunction, is_num
from .options import load_jscs, pick_table


def _kv_list(pairs, cast=str):
    out = {}
    for raw in pairs or []:
        if '=' not in raw:
            raise SystemExit('veladec: expected NAME=VALUE, got %r' % raw)
        k, v = raw.split('=', 1)
        try:
            out[k] = cast(v)
        except Exception:
            out[k] = v
    return out


def _parse_stop(raw):
    """'2d6' breaks the first time, '2d6:3' the third time.

    A leading 'FN@' scopes the offset to one function: '7@2d6:2'.
    """
    fn = None
    if '@' in raw:
        head, raw = raw.split('@', 1)
        fn = int(head)
    pos, _, nth = raw.partition(':')
    return (fn, int(pos, 16), int(nth) if nth else 1)


def _json_arg(raw, what):
    if raw is None:
        return None
    try:
        return from_plain(json.loads(raw))
    except Exception as e:
        raise SystemExit('veladec: bad JSON in %s: %s' % (what, e))


def _find_method(m, name):
    """fn index of a function bound to `name` in some module object literal."""
    for fn_idx, lit in enumerate(m.literals):
        for field, kind, val in lit:
            if kind == 'fn' and field == name:
                return val
    return None


def _find_fn(interp, idx):
    """A closure created by an earlier call: (function, owning object).

    The owner matters: a page method needs its page object as ``this``, so a
    function found inside an object literal hands that object back with it.
    """
    for frame in list(interp.frames_kept.values())[::-1]:
        pool = list(frame.loc) + list(frame.arg)
        pool += [getattr(r, 'v', r) for r in frame.refs]
        for v in pool:
            if isinstance(v, JSFunction) and v.index == idx:
                return v, None
            if isinstance(v, (dict, list)):
                items = list(v.values()) if isinstance(v, dict) else [v]
                for x in items:
                    if isinstance(x, JSFunction) and x.index == idx:
                        return x, v
                    if isinstance(x, dict):
                        for y in x.values():
                            if isinstance(y, JSFunction) and y.index == idx:
                                return y, x
    return None, None


def cmd_run(args, opts):
    t = Target(args.target)
    ops, note = pick_table(t, opts, args.table)
    if note and not args.quiet:
        print('// %s' % note, file=sys.stderr)

    files = [(rel, j) for rel, j in load_jscs(t, opts)
             if not args.file or args.file in rel]
    if not files:
        print('veladec: no .jsc matched', file=sys.stderr)
        return 2

    rel, jsc = files[0]
    fn_index = args.fn
    if args.method:
        for rel2, j2 in files:
            m = Map(rel2, j2, ops)
            idx = _find_method(m, args.method)
            if idx is not None:
                rel, jsc, fn_index = rel2, j2, idx
                break
        if fn_index is None:
            print('veladec: no method named %r in a module literal' % args.method,
                  file=sys.stderr)
            return 2
    if fn_index is None:
        print('veladec: --fn N or --method NAME is required', file=sys.stderr)
        return 2

    fn = None
    for i, f in enumerate(jsc.functions):
        if i == fn_index:
            fn = f
            break
    if fn is None:
        print('veladec: no function %d in %s' % (fn_index, rel), file=sys.stderr)
        return 2

    argv = _json_arg(args.args, '--args') or []
    if not isinstance(argv, list):
        argv = [argv]
    this = _json_arg(args.this, '--this')
    if this is None:
        this = None if args.null_this else U
    globals_extra = {k: _json_arg(v, '--global %s' % k)
                     for k, v in _kv_list(args.global_, str).items()}
    storage = _kv_list(args.storage, str)
    atom_override = {}
    for raw in args.atom or []:
        if '=' not in raw:
            raise SystemExit('veladec: --atom wants ID=NAME, got %r' % raw)
        k, v = raw.split('=', 1)
        try:
            atom_override[int(k.rstrip('bB'))] = v
        except ValueError:
            raise SystemExit('veladec: --atom id must be an integer, got %r' % k)

    host = Host(storage=storage, device_id=args.device_id, now=args.now,
                globals_extra=globals_extra, rng_seed=args.seed)
    interp = Interp(jsc, ops, host,
                    max_steps=args.max_steps,
                    trace=args.trace,
                    trace_calls=args.trace_calls,
                    watch=args.watch or (),
                    watch_calls=args.watch_call or (),
                    stop_at=({None: _parse_stop(args.stop_at)}
                             if args.stop_at else None),
                    sink=(lambda s: print(s, file=sys.stderr)),
                    atoms=atom_override,
                    snaps=[_parse_stop(r) for r in (args.snap or [])],
                    fill=args.fill)
    interp._load_atoms(getattr(opts, 'builtin_atoms', None))

    err = None
    fnobj = JSFunction(fn, [], index=fn_index)
    try:
        value = interp.call(fnobj, argv, this)
    except UnsupportedOpcode as e:
        value, err = None, str(e)
    except _Throw as e:
        value, err = None, 'uncaught %r' % (e.value,)
    except RecursionError:
        value, err = None, 'recursion limit (nested bytecode calls)'

    then_note = None
    for spec in args.then or []:
        m = re.match(r'^\s*(\d+)\s*(?::(.*))?$', spec, re.S)
        fn_s = m.group(1) if m else spec
        arg_s = (m.group(2) or '').strip() if m else ''
        try:
            want = int(fn_s)
        except ValueError:
            then_note = 'bad --then spec %r' % spec
            value, err = None, then_note
            break
        target, owner = _find_fn(interp, want)
        if target is None:
            then_note = 'fn[%d] was not created by %s' % (want, 'the entry call')
            value, err = None, then_note
            break
        if arg_s:
            try:
                t_args = from_plain(json.loads(arg_s))
            except Exception as e:
                then_note = 'bad JSON in --then %s: %s' % (spec, e)
                value, err = None, then_note
                break
        else:
            t_args = _json_arg(args.then_args, '--then-args') or []
        if not isinstance(t_args, list):
            t_args = [t_args]
        t_this = _json_arg(args.then_this, '--then-this')
        if t_this is None:
            t_this = owner if owner is not None else U
        try:
            value = interp.call(target, t_args, t_this)
        except UnsupportedOpcode as e:
            value, err = None, str(e)
            break
        except _Throw as e:
            value, err = None, 'uncaught %r' % (e.value,)
            break

    stopped = interp.stopped
    if args.json:
        print(json.dumps({
            'file': rel,
            'fn': fn_index,
            'name': fn.get('name'),
            'value': to_plain(value) if err is None else None,
            'error': err,
            'stopped': stopped,
            'steps': interp.steps,
            'calls': [{'fn': c['fn'], 'name': c['name'],
                       'args': [to_plain(a) for a in c['args']],
                       'depth': c['depth'],
                       'result': to_plain(c.get('result'))}
                      for c in interp.calls],
            'watch': [{'kind': e['kind'], 'name': e['name'], 'fn': e['fn'],
                       'pos': e['pos'], 'value': to_plain(e['value'])}
                      for e in interp.events],
            'host': host.rec.to_json(),
        }, ensure_ascii=False, indent=2))
        return 0 if err is None else 1

    if not args.quiet:
        man = t.manifest or {}
        print('# veladec %s run -- dynamic analysis' % __version__)
        print('# %s %s' % (man.get('name') or '', rel))
        print('# fn[%d] %s  args=%d vars=%d closures=%d cpool=%d'
              % (fn_index, fn.get('name') or '?', fn['arg_count'],
                 fn['var_count'], len(fn.get('closure_vars') or []),
                 len(fn.get('cpool') or [])))
        print('# steps=%d  calls=%d  stopped=%s'
              % (interp.steps, len(interp.calls), stopped))

    for call in interp.calls:
        if not (args.trace_calls or call['fn'] in (args.watch_call or [])):
            continue
        print('call fn[%s] %s(%s)%s'
              % (call['fn'], call['name'] or '?',
                 ', '.join(_fmt(a) for a in call['args']),
                 '  = ' + _fmt(call.get('result')) if 'result' in call else ''))
    for e in host.rec.rows:
        print('host %-24s %s%s'
              % (e['api'], ', '.join(_fmt(a) for a in e['args']),
                 '  -> ' + _fmt(e['result'])))
    for snap in getattr(interp, 'snapshots', ()):
        print('snap fn[%s]:0x%04x  %s'
              % (snap['fn'], snap['pos'],
                 '  '.join('r%d=%s' % (i, _fmt(v))
                           for i, v in enumerate(snap['loc']) if v is not U)))
    for aid, name, fidx, pos in getattr(interp, 'atom_notes', ()):
        print('atom  $k%-4d -> %-16s (fn[%s]:0x%04x)' % (aid, name, fidx, pos))
    for e in interp.events:
        print('watch %s %-18s <- %s   (fn[%s]:0x%04x)'
              % (e['kind'], e['name'], _fmt(e['value']), e['fn'], e['pos']))

    if err:
        print('error: %s' % err)
        return 1
    print('result: %s' % _fmt(value))
    if args.dump:
        _dump(interp, fn_index)
    return 0


def _fmt(v):
    from ..rt.values import to_str as s
    plain = to_plain(v)
    if isinstance(plain, str):
        return repr(plain) if len(plain) < 200 else repr(plain[:197] + '...')
    if isinstance(plain, (dict, list)):
        raw = json.dumps(plain, ensure_ascii=False)
        return raw if len(raw) < 240 else raw[:237] + '...'
    return s(plain) if plain is None else json.dumps(plain, ensure_ascii=False)


def _dump(interp, index):
    f = getattr(interp, 'brk', None)
    if f is None:
        print('dump: no frame captured (set --stop-at to break inside)')
        return
    print('dump fn[%s] at 0x%04x' % (f.index, f.pos))
    for i, v in enumerate(f.loc):
        if v is not None:
            print('  r%-3d %s' % (i, _fmt(v)))
    for i, v in enumerate(f.arg):
        print('  a%-3d %s' % (i, _fmt(v)))
    for i, cell in enumerate(f.refs):
        print('  c%-3d %s' % (i, _fmt(getattr(cell, 'v', cell))))
    print('  stack %s' % ', '.join(_fmt(x) for x in f.st[-8:]))
