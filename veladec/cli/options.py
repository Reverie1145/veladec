"""Command-line options and target/table selection."""

import json

from ..builtins import BUILTINS
from ..ins import OpTable, validate
from ..ser import JscFile
from ..tables import OPCODE_TABLES


DEFAULT_TARGET = '2020-11-08'


class Opts:
    def __init__(self, args):
        self.indent = args.indent
        self.offsets = getattr(args, 'offsets', False)
        self.structure = not getattr(args, 'no_structure', False)
        self.labels = not getattr(args, 'no_labels', False)
        self.atom_base = args.atom_base
        self.builtins = dict(BUILTINS)
        if getattr(args, 'builtins_file', None):
            with open(args.builtins_file) as fh:
                extra = json.load(fh)
            self.builtins.update({int(k): v for k, v in extra.items()})


def load_jscs(target, opts):
    out = []
    for rel, data in sorted(target.files.items()):
        out.append((rel, JscFile(data, opts.atom_base, opts.builtins)))
    return out


def pick_table(target, opts, requested):
    """Resolve the opcode table, auto-detecting the release if asked."""
    if requested and requested != 'auto':
        return OpTable(requested), None
    sample = []
    for rel, data in sorted(target.files.items()):
        sample.append(JscFile(data, opts.atom_base, opts.builtins))
        if len(sample) >= 2:
            break
    scores = {}
    for v in OPCODE_TABLES:
        ops = OpTable(v)
        tot = 0
        exact = 0
        for j in sample:
            r = validate(j, ops)
            tot += r['penalty']
            exact += r['not_exact']
        scores[v] = (tot, exact)
    best = min(scores, key=lambda v: scores[v])
    detail = ', '.join('%s=%d' % (v, scores[v][0]) for v in sorted(scores))
    return OpTable(best), 'auto-selected %s (penalty: %s)' % (best, detail)


def iter_funcs(jsc, ops, opts):
    entry = jsc.module.get('func')
    if entry:
        yield ('entry', entry, None)
    for i, f in enumerate(jsc.functions):
        yield (i, f, i)
