"""Inspection commands: info, unpack, ls, strings, search, selftest, tables."""

import re
import sys

from .. import __version__
from ..decomp import FuncRenderer, jsstr
from ..ins import OpTable, validate
from ..rpk import Target, dump_files
from ..tables import OPCODE_TABLES
from .options import DEFAULT_TARGET, iter_funcs, load_jscs, pick_table


def cmd_info(args, opts):
    t = Target(args.target)
    ops, note = pick_table(t, opts, args.table)
    s = t.summary()
    print('target      : %s (%s)' % (s['path'], s['kind']))
    if s['package']:
        print('package     : %s  "%s"' % (s['package'], s['name']))
        print('version     : %s   minPlatform=%s   deviceType=%s'
              % (s['version'], s['minPlatformVersion'], s['deviceType']))
        print('toolkit     : %s' % s['toolkit'])
        print('features    : %s' % ', '.join(s['features']))
        print('pages       : %s' % s['pages'])
    print('opcode table: %s%s' % (ops.version, ('   [%s]' % note) if note else ''))
    print()
    print('%-28s %6s %6s %9s %6s %s' % ('file', 'atoms', 'funcs', 'insns', 'exact', 'anomalies'))
    tot = dict(files=0, atoms=0, funcs=0, insns=0, bad=0, anom=0, trailing=0)
    for rel, j in load_jscs(t, opts):
        r = validate(j, ops)
        anoms = 0
        for idx, f, _ in iter_funcs(j, ops, opts):
            rr = FuncRenderer(j, ops, f, opts, index=idx)
            rr.render()
            anoms += len(rr.anoms)
        tot['files'] += 1
        tot['atoms'] += len(j.atoms)
        tot['funcs'] += r['functions']
        tot['insns'] += r['instructions']
        tot['bad'] += r['penalty']
        tot['anom'] += anoms
        tot['trailing'] += j.trailing
        print('%-28s %6d %6d %9d %6s %d%s'
              % (rel, len(j.atoms), r['functions'], r['instructions'],
                 'yes' if r['not_exact'] == 0 else 'NO', anoms,
                 '' if not j.trailing else '  trailing=%d' % j.trailing))
    print()
    print('%d file(s), %d atoms, %d functions, %d instructions, structural penalties=%d, '
          'renderer anomalies=%d, trailing bytes=%d'
          % (tot['files'], tot['atoms'], tot['funcs'], tot['insns'], tot['bad'],
             tot['anom'], tot['trailing']))
    return 0


def cmd_unpack(args, opts):
    t = Target(args.target)
    rows = dump_files(t, args.out)
    for rel, dst, n in rows:
        print('%-40s %8d  -> %s' % (rel, n, dst))
    print('%d file(s)' % len(rows))
    return 0


def cmd_ls(args, opts):
    t = Target(args.target)
    ops, _ = pick_table(t, opts, args.table)
    pat = re.compile(args.grep, re.I) if args.grep else None
    for rel, j in load_jscs(t, opts):
        if args.file and args.file not in rel:
            continue
        print('== %s  (atoms=%d)' % (rel, len(j.atoms)))
        print('%5s %-32s %5s %5s %6s %8s %s'
              % ('idx', 'name', 'args', 'vars', 'stack', 'bytes', 'insns'))
        for idx, f, _ in iter_funcs(j, ops, opts):
            nm = f['name'] or '<anon>'
            if pat and not pat.search(nm):
                continue
            ins, _ok, _ex = ops.decode(f['bytecode'])
            print('%5s %-32s %5d %5d %6d %8d %d'
                  % (idx, nm[:32], f['arg_count'], f['var_count'],
                     f['stack_size'], f['byte_code_len'], len(ins)))
    return 0


def cmd_strings(args, opts):
    t = Target(args.target)
    pat = re.compile(args.grep, re.I) if args.grep else None
    for rel, j in load_jscs(t, opts):
        if args.file and args.file not in rel:
            continue
        print('== %s  (%d atoms)' % (rel, len(j.atoms)))
        for i, a in enumerate(j.atoms):
            if pat and not pat.search(a):
                continue
            if len(a) < args.min:
                continue
            print('%5d (k=%d)  %s' % (i, i + opts.atom_base, jsstr(a)))
    return 0


def cmd_search(args, opts):
    t = Target(args.target)
    pat = re.compile(args.pattern if args.regex else re.escape(args.pattern), re.I)
    hits = 0
    for rel, j in load_jscs(t, opts):
        for i, a in enumerate(j.atoms):
            if pat.search(a):
                hits += 1
                print('%s  atom[%d] = %s' % (rel, i, jsstr(a)[:200]))
    print('%d hit(s)' % hits, file=sys.stderr)
    return 0 if hits else 1


def cmd_selftest(args, opts):
    t = Target(args.target)
    print('version: veladec %s' % __version__)
    rows = []
    for v in (OPCODE_TABLES if args.all_tables else [DEFAULT_TARGET]):
        ops = OpTable(v)
        agg = dict(functions=0, instructions=0, penalty=0, not_exact=0,
                   unknown_opcode=0, bad_jump=0, bad_atom=0, bad_pool=0, bad_slot=0)
        for rel, j in load_jscs(t, opts):
            r = validate(j, ops)
            for k in agg:
                agg[k] += r[k]
        rows.append((v, agg))
        print('%-12s funcs=%-6d insns=%-7d penalty=%-6d not_exact=%-4d '
              'unknown=%-5d badjump=%-5d badatom=%-4d badpool=%-4d badslot=%d'
              % (v, agg['functions'], agg['instructions'], agg['penalty'],
                 agg['not_exact'], agg['unknown_opcode'], agg['bad_jump'],
                 agg['bad_atom'], agg['bad_pool'], agg['bad_slot']))
    if args.all_tables:
        best = min(rows, key=lambda r: (r[1]['penalty'], r[1]['not_exact']))
        print('\nbest table: %s' % best[0])
    # round-trip check: re-parse every file and compare instruction stream
    bad = 0
    for rel, j in load_jscs(t, opts):
        if j.trailing:
            print('  %s: %d trailing byte(s)' % (rel, j.trailing))
            bad += 1
        total = sum(f['byte_code_len'] for f in j.functions)
        decoded = 0
        for f in j.functions:
            ins, ok, exact = OpTable(DEFAULT_TARGET).decode(f['bytecode'])
            decoded += sum(i.size for i in ins)
            if not exact:
                bad += 1
        if decoded != total:
            print('  %s: decoded %d != byte_code_len %d' % (rel, decoded, total))
            bad += 1
    print('\nselftest: %s' % ('OK' if bad == 0 else '%d problem(s)' % bad))
    return 0 if bad == 0 else 3


def cmd_tables(args, opts):
    print('%5s %6s %6s %6s  %s' % ('bytes', 'pre', 'temps', 'short', 'release'))
    for v, d in sorted(OPCODE_TABLES.items()):
        nshort = len(d['short'])
        print('%5d %6d %6d %6d  %s' % (d['K'] + nshort, d['K'], 0, nshort, v))
    print('\ndefault: %s' % DEFAULT_TARGET)
    print('note: the OP_TEMP_* opcodes occupy byte values but never appear in'
          ' serialized bytecode, so they are not stored in the tables.')
    return 0
