#!/usr/bin/env python3
"""Calibrate the bytecode atom base (`--atom-base`) for an unknown toolchain.

A field-access opcode (``get_field`` / ``define_field`` / …) can only reference
an atom that looks like an identifier, so the correct base is the one where the
largest fraction of field-position atoms resolve to identifier-shaped names.
The score jumps to ~1.00 at the right base and degrades sharply around it.

    python3 tools/calib_atom_base.py pages/index/index.jsc
    python3 tools/calib_atom_base.py index.jsc --lo 190 --hi 240 -n 8
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from veladec.ser import JscFile                      # noqa: E402
from veladec.ins import OpTable                      # noqa: E402

FIELD_OPS = {'get_field', 'get_field2', 'get_field_opt_chain', 'put_field',
             'define_field', 'define_field2', 'define_method', 'set_name'}
IDENT = re.compile(r'^[A-Za-z_$][A-Za-z0-9_$]*$')


def collect(jsc, ops):
    """-> list of raw atom operands seen at field positions."""
    out = []
    for f in jsc.walk():
        ins, _ok, _exact = ops.decode(f['bytecode'])
        for i in ins:
            base, _inline = ops.normalize(i.name)
            if base in FIELD_OPS and i.extra and i.extra[0] == 'atom':
                out.append(i.extra[1] & 0x7FFFFFFF)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('jsc')
    ap.add_argument('--lo', type=int, default=190)
    ap.add_argument('--hi', type=int, default=250)
    ap.add_argument('-n', type=int, default=6, help='how many candidates to print')
    ap.add_argument('--table', default='2020-11-08')
    a = ap.parse_args()

    jsc = JscFile(open(a.jsc, 'rb').read())
    ops = OpTable(a.table)
    raws = collect(jsc, ops)
    if not raws:
        sys.exit('no field-position atom operands found')

    scores = []
    for base in range(a.lo, a.hi + 1):
        hit = tot = 0
        for r in raws:
            k = r - base
            tot += 1
            if 0 <= k < len(jsc.atoms) and IDENT.match(jsc.atoms[k] or ''):
                hit += 1
        scores.append((hit / tot, base))
    scores.sort(reverse=True)

    print('%s: %d field-position atom operands, %d atoms in table'
          % (os.path.basename(a.jsc), len(raws), len(jsc.atoms)))
    for ratio, base in scores[:a.n]:
        print('  atom-base %-4d ident-ratio %.4f' % (base, ratio))
    best = scores[0]
    print('suggest: --atom-base %d   (ident-ratio %.4f)' % (best[1], best[0]))


if __name__ == '__main__':
    main()
