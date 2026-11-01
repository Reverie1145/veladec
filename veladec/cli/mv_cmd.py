"""mv: print the module / view map for every .jsc in a target."""

import os
import sys

from .. import __version__
from ..mv import Map, _detail, render_json, render_md, render_text
from ..rpk import Target
from .options import load_jscs, pick_table


def cmd_mv(args, opts):
    t = Target(args.target)
    ops, note = pick_table(t, opts, args.table)
    if note and not args.quiet:
        print('// %s' % note, file=sys.stderr)

    maps = []
    for rel, j in load_jscs(t, opts):
        if args.file and args.file not in rel:
            continue
        maps.append(Map(rel, j, ops))
    if not maps:
        print('veladec: no .jsc matched%s'
              % (' --file %r' % args.file if args.file else ''), file=sys.stderr)
        return 2

    man = t.manifest or {}
    label = ' '.join(x for x in (man.get('name'), man.get('versionName')) if x)
    header = ['# veladec %s mv -- module / view map' % __version__,
              '# %s%s' % (os.path.basename(t.path.rstrip('/')),
                          '   ' + label if label else ''),
              '# table %s, atom base %d' % (ops.version, opts.atom_base)]

    if args.fn is not None:
        keep = [m for m in maps if any(m.idx.get(id(f)) == args.fn
                                       for f in m.jsc.functions)]
        if not keep:
            print('veladec: no function %d in the selected files' % args.fn,
                  file=sys.stderr)
            return 2
        m = keep[0]
        sys.stdout.write('%s\n# %s\n' % (header[0], m.rel))
        sys.stdout.write('\n'.join(_detail(m, args.fn)) + '\n')
        return 0

    fmt = args.format
    ext = {'json': 'json', 'md': 'md'}.get(fmt, 'txt')

    def chunk(m):
        if fmt == 'json':
            return render_json([m], header)
        if fmt == 'md':
            return render_md([m], header, args.grep, args.names)
        return render_text([m], header, args.grep, args.names)

    if args.stdout or not args.out:
        sys.stdout.write(render_json(maps, header) if fmt == 'json'
                         else ''.join(chunk(m) for m in maps))
        return 0
    n = 0
    for m in maps:
        dst = os.path.join(args.out,
                           m.rel.replace('/', '_').replace('.jsc', '') + '.mv.' + ext)
        os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
        with open(dst, 'w', encoding='utf-8') as fh:
            fh.write(chunk(m))
        n += 1
    if not args.quiet:
        print('%d file(s) -> %s' % (n, args.out))
    return 0
