#!/usr/bin/env python3
"""Regenerate the veladec/tables package from official QuickJS source releases.

Usage:
    python3 tools/gen_tables.py --src /path/to/qjs [--out veladec/tables]

`--src` may be either

  * a directory whose children are extracted source trees, i.e.
    ``<src>/2020-11-08/quickjs-opcode.h`` (+ ``quickjs-atom.h``), or
  * a flat directory of header copies named ``quickjs-opcode.h`` only
    (version taken from the parent directory name).

Output is one module per release (``tables/v2020_11_08.py``, holding ``K``,
``PRE``, ``SHORT`` and ``ATOMS``) plus a ``tables/__init__.py`` that assembles
them back into ``OPCODE_TABLES`` / ``ATOM_TABLES``.

Every version found is (re)generated; versions already present in the
destination but missing from ``--src`` are kept as they are, so adding one
new toolchain never drops the others.
"""
import argparse
import os
import re
import sys

ATOM_RE = re.compile(r'^\s*DEF\(\s*(\w+)\s*,\s*"', re.M)

MODULE_HEADER = '''"""QuickJS {ver}: opcode and predefined-atom tables (generated).

Do not edit by hand -- regenerate with tools/gen_tables.py.
"""

# number of "pre" opcodes; short opcodes are numbered K + index
K = {K}

PRE = [
{pre}]

SHORT = [
{short}]

ATOMS = [
{atoms}]
'''

INIT_HEADER = '''"""QuickJS opcode / predefined-atom tables, one module per release.

Source: quickjs-opcode.h + quickjs-atom.h from official QuickJS releases
(https://bellard.org/quickjs/).  Regenerate with tools/gen_tables.py.

Each ``v<release>.py`` module exposes:

  ``K``      number of "pre" opcodes (short opcodes are numbered ``K + i``)
  ``PRE``    [(name, size, npop, npush, fmt), ...] -- the plain opcodes
  ``SHORT``  same shape -- the ``SHORT_OPCODES`` variants
  ``ATOMS``  predefined atom names, indexed by atom id
"""

{imports}

_MODULES = {{
{table}}}

OPCODE_TABLES = {{ver: {{'K': m.K, 'pre': m.PRE, 'short': m.SHORT}}
                 for ver, m in _MODULES.items()}}

ATOM_TABLES = {{ver: m.ATOMS for ver, m in _MODULES.items()}}

RELEASES = tuple(_MODULES)
'''


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


def load_existing(out):
    """Merge with what is already on disk, so partial runs never drop versions."""
    pkg = os.path.dirname(os.path.dirname(os.path.abspath(out)))
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    try:
        from veladec import tables as t           # noqa: WPS433 (runtime import)
        return dict(t.OPCODE_TABLES), dict(t.ATOM_TABLES)
    except Exception:
        return {}, {}
    finally:
        if sys.path and sys.path[0] == pkg:
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


def module_name(ver):
    return 'v' + ver.replace('-', '_').replace('.', '_')


def render_module(ver, ops, atoms):
    def recs(items):
        return ''.join('    %r,\n' % (tuple(rec),) for rec in items)

    return MODULE_HEADER.format(
        ver=ver,
        K=ops['K'],
        pre=recs(ops['pre']),
        short=recs(ops['short']),
        atoms=''.join('    %r,\n' % n for n in atoms),
    )


def render_init(versions):
    imports = '\n'.join('from . import %s' % module_name(v) for v in versions)
    table = '\n'.join('    %r: %s,' % (v, module_name(v)) for v in versions)
    return INIT_HEADER.format(imports=imports, table=table)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', default='veladec/tables',
                    help='destination package directory')
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

    versions = sorted(ops)
    os.makedirs(a.out, exist_ok=True)
    for ver in versions:
        path = os.path.join(a.out, module_name(ver) + '.py')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(render_module(ver, ops[ver], atoms.get(ver, [])))
        print('wrote', path)
    with open(os.path.join(a.out, '__init__.py'), 'w', encoding='utf-8') as fh:
        fh.write(render_init(versions))
    print('wrote', os.path.join(a.out, '__init__.py'))


if __name__ == '__main__':
    main()
