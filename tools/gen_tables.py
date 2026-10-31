#!/usr/bin/env python3
"""Regenerate veladec/tables.py from official QuickJS source releases.

Usage:
    python3 tools/gen_tables.py --src /path/to/qjs [--out veladec/tables.py]

`--src` may be either

  * a directory whose children are extracted source trees, i.e.
    ``<src>/2020-11-08/quickjs-opcode.h`` (+ ``quickjs-atom.h``), or
  * a flat directory of header copies named ``quickjs-opcode.h`` only
    (version taken from the parent directory name).

Every version found is (re)generated; versions already present in the
destination file but missing from ``--src`` are kept as they are, so adding one
new toolchain never drops the others.
"""
import argparse
import os
import re
import sys

DEF_RE = re.compile(r'^\s*DEF\(\s*(\w+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\w+)', re.M)
TEMPDEF_RE = re.compile(r'^\s*def\(\s*(\w+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\w+)', re.M)
ATOM_RE = re.compile(r'^\s*DEF\(\s*(\w+)\s*,\s*"', re.M)


def parse_opcode_header(text):
    """-> (K, pre, short) where each entry is (name, size, npop, npush, fmt)."""
    pre, short = [], []
    stack = []                  # conditional-compilation frames
    skip = False                # inside `#ifdef CONFIG_BIGNUM` (build has it off)
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('#if'):
            cond = s
            stack.append(cond)
            if 'CONFIG_BIGNUM' in cond:
                skip = True
            elif 'SHORT_OPCODES' in cond:
                stack[-1] = '#SHORT'
            continue
        if s.startswith('#else') or s.startswith('#elif'):
            if stack and 'CONFIG_BIGNUM' in stack[-1]:
                skip = False       # the #else branch is the normal build
            continue
        if s.startswith('#endif'):
            if stack:
                if 'CONFIG_BIGNUM' in stack.pop():
                    skip = False
            continue
        if skip:
            continue
        in_short = bool(stack) and stack[-1] == '#SHORT'
        m = re.match(r'^(DEF|def)\(\s*(\w+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\w+)', s)
        if not m:
            continue
        kind, name, size, npop, npush, fmt = m.groups()
        rec = (name, int(size), int(npop), int(npush), fmt)
        if kind == 'def':
            continue                     # temp opcodes: not addressable by name
        (short if in_short else pre).append(rec)
    return len(pre), pre, short


def parse_atom_header(text):
    # the enum identifier is what the index maps to (e.g. `null`, `_eval_`)
    return ATOM_RE.findall(text)


def load_existing(path):
    if not os.path.exists(path):
        return {}, {}
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(path))))
    try:
        from veladec import tables as t           # noqa
        return dict(t.OPCODE_TABLES), dict(t.ATOM_TABLES)
    finally:
        sys.path.pop(0)


def find_trees(src):
    found = {}
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if not os.path.isdir(d):
            continue
        op = os.path.join(d, 'quickjs-opcode.h')
        if os.path.exists(op):
            ver = re.sub(r'^quickjs-', '', name)
            found[ver] = d
    # nested (e.g. src/v2021/quickjs-2021-03-27)
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if not os.path.isdir(d):
            continue
        for sub in sorted(os.listdir(d)):
            sd = os.path.join(d, sub)
            if os.path.isdir(sd) and os.path.exists(os.path.join(sd, 'quickjs-opcode.h')):
                ver = sub.replace('quickjs-', '')
                found.setdefault(ver, sd)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', default='veladec/tables.py')
    a = ap.parse_args()

    ops, atoms = load_existing(a.out)
    for ver, d in find_trees(a.src).items():
        op = open(os.path.join(d, 'quickjs-opcode.h'), encoding='utf-8', errors='replace').read()
        K, pre, short = parse_opcode_header(op)
        ops[ver] = {'K': K, 'pre': pre, 'short': short}
        apath = os.path.join(d, 'quickjs-atom.h')
        if os.path.exists(apath):
            atoms[ver] = parse_atom_header(open(apath, encoding='utf-8', errors='replace').read())
        print('%-12s K=%-4d pre=%-4d short=%-3d atoms=%d'
              % (ver, K, len(pre), len(short), len(atoms.get(ver, []))))

    out = ['"""Auto-generated QuickJS opcode / predefined-atom tables (do not edit by hand).',
           '',
           'Source: quickjs-opcode.h + quickjs-atom.h from official QuickJS releases',
           '(https://bellard.org/quickjs/).  Regenerate with tools/gen_tables.py.',
           '"""',
           '',
           'OPCODE_TABLES = {']
    for ver in sorted(ops):
        d = ops[ver]
        out.append("  %r: {" % ver)
        out.append("    'K': %d," % d['K'])
        for key in ('pre', 'short'):
            out.append("    '%s': [" % key)
            for rec in d[key]:
                out.append('      %r,' % (tuple(rec),))
            out.append('    ],')
        out.append('  },')
    out.append('}')
    out.append('')
    out.append('ATOM_TABLES = {')
    for ver in sorted(atoms):
        out.append("  %r: [" % ver)
        for n in atoms[ver]:
            out.append('    %r,' % n)
        out.append('  ],')
    out.append('}')
    open(a.out, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('wrote', a.out)


if __name__ == '__main__':
    main()
