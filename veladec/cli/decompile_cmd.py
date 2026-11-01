"""decompile / disasm: render .jsc files back to source or assembly."""

import os
import sys

from ..decomp import decompile_file
from ..rpk import Target
from .asm import asm_lines
from .formats import out_html, out_js, out_json, out_md
from .options import iter_funcs, load_jscs, pick_table


def cmd_decompile(args, opts):
    t = Target(args.target)
    ops, note = pick_table(t, opts, args.table)
    if note and not args.quiet:
        print('// %s' % note, file=sys.stderr)
    files = []
    for rel, j in load_jscs(t, opts):
        if args.file and args.file not in rel:
            continue
        sections = decompile_file(j, ops, opts, opts.builtins)
        if args.fn is not None:
            keep = [f for f in sections['functions'] if f['index'] == args.fn]
            sections = {'module': sections['module'], 'functions': keep}
        files.append((rel, sections))

    fmt = args.format
    if fmt == 'json':
        return _write(args, out_json(files, opts), 'json')
    if fmt == 'html':
        man = t.manifest or {}
        label = man.get('name') and '%s %s' % (man['name'], man.get('versionName', ''))
        title = args.title or label or man.get('package') or os.path.basename(
            t.path.rstrip('/')).replace('.rpk', '') or 'veladec'
        return _write(args, out_html(files, title, opts), 'html')
    if fmt == 'md':
        return _write(args, '\n'.join(out_md(s, n, opts) for n, s in files), 'md')
    # js: one file per .jsc unless --stdout / --single
    if args.stdout or args.fn is not None:
        chunks = [out_js(s, n, opts) for n, s in files]
        sys.stdout.write('\n'.join(chunks))
        return 0
    outdir = args.out or 'veladec-out'
    n = 0
    for name, sections in files:
        dst = os.path.join(outdir, name.replace('/', '_').replace('.jsc', '') + '.pseudo.js')
        os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
        with open(dst, 'w', encoding='utf-8') as fh:
            fh.write(out_js(sections, name, opts))
        n += 1
        if not args.quiet:
            print('wrote %s' % dst)
    if not args.quiet:
        print('%d file(s) -> %s' % (n, outdir))
    return 0


def _write(args, text, ext):
    if args.stdout:
        sys.stdout.write(text)
        return 0
    outdir = args.out or 'veladec-out'
    os.makedirs(outdir, exist_ok=True)
    dst = os.path.join(outdir, 'report.' + ext)
    with open(dst, 'w', encoding='utf-8') as fh:
        fh.write(text)
    if not args.quiet:
        print('wrote %s' % dst)
    return 0


def cmd_disasm(args, opts):
    t = Target(args.target)
    ops, note = pick_table(t, opts, args.table)
    if note and not args.quiet:
        print('; %s' % note, file=sys.stderr)
    out = []
    for rel, j in load_jscs(t, opts):
        if args.file and args.file not in rel:
            continue
        out.append('; ==== %s  atoms=%d' % (rel, len(j.atoms)))
        for idx, f, _ in iter_funcs(j, ops, opts):
            if args.fn is not None and idx != args.fn:
                continue
            if args.fn is None and args.name and args.name not in (f['name'] or ''):
                continue
            ins, _ok, _ex = ops.decode(f['bytecode'])
            out.append('')
            out.append('; --- fn[%s] %s  args=%d vars=%d closure=%d stack=%d bc=%dB insns=%d'
                       % (idx, f['name'] or '<anon>', f['arg_count'], f['var_count'],
                          f['closure_var_count'], f['stack_size'],
                          f['byte_code_len'], len(ins)))
            out.extend(asm_lines(j, ops, f))
    text = '\n'.join(out) + '\n'
    if args.stdout or args.fn is not None or args.name:
        sys.stdout.write(text)
        return 0
    outdir = args.out or 'veladec-out'
    os.makedirs(outdir, exist_ok=True)
    dst = os.path.join(outdir, 'all.asm')
    with open(dst, 'w', encoding='utf-8') as fh:
        fh.write(text)
    if not args.quiet:
        print('wrote %s' % dst)
    return 0
