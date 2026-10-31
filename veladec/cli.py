"""veladec command line interface."""

import argparse
import html
import json
import os
import re
import sys

from . import __version__
from .builtins import BUILTINS
from .ins import OpTable, validate, autodetect, resolve_label, JUMP_FMTS
from .decomp import FuncRenderer, decompile_file, jsstr
from .rpk import Target, dump_files
from .ser import JscFile, ATOM_BASE_DEFAULT
from .tables import OPCODE_TABLES

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


# ----------------------------------------------------------------- helpers
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


def asm_lines(jsc, ops, f, show_atoms=True):
    ins, ok, exact = ops.decode(f['bytecode'])
    out = []
    for i in ins:
        txt = ''
        if i.extra and i.extra[0] == 'atom' and show_atoms:
            txt = '  ; %s' % jsc.atom(i.extra[1])
        elif i.fmt in JUMP_FMTS:
            t = resolve_label(ins, i.pos, i.extra[1], i.fmt)
            txt = '  ; -> %s' % ('L%04x' % t if t is not None else 'unresolved')
        elif i.fmt == 'const' and i.extra:
            v = f['cpool'][i.extra[1]] if i.extra[1] < len(f['cpool']) else None
            txt = '  ; %s' % (('<fn:%s>' % (v.get('name') or 'anon'))
                              if isinstance(v, dict) else jsstr(v))
        out.append('%04x  %-18s %-14s%s' % (i.pos, i.name, i.text, txt))
    out.append('%s  ; exact=%s len=%d' % ('.' * 8, exact, len(f['bytecode'])))
    return out


def render_lines(lines):
    return '\n'.join(('    ' * l.depth) + l.text for l in lines)


# ----------------------------------------------------------------- formats
def out_js(sections, name, opts):
    head = ['// %s' % name,
            '// decompiled by veladec %s -- pseudo-JS, goto-preserving' % __version__]
    body = list(head)
    if sections['module']:
        body.append('// --- module entry: %s' % sections['module']['sig'])
        body.append(render_lines(sections['module']['lines']))
    for fn in sections['functions']:
        body.append('')
        body.append('// --- %s' % fn['sig'])
        body.append(render_lines(fn['lines']))
    return '\n'.join(body) + '\n'


def out_md(sections, name, opts):
    body = ['# %s' % name, '',
            '`veladec %s` pseudo-JS output. `goto` is preserved; block structure '
            'is recovered only where provably safe.' % __version__, '']
    if sections['module']:
        body += ['## module entry', '```js', render_lines(sections['module']['lines']),
                 '```', '']
    for fn in sections['functions']:
        body += ['## %s' % fn['sig'], '```js', render_lines(fn['lines']), '```', '']
    return '\n'.join(body)


_JS_TOKEN = re.compile(r'("(?:[^"\\]|\\.)*")|(//[^\n]*)|\b(%s)\b'
                       % '|'.join(('if', 'else', 'while', 'for', 'return', 'throw',
                                   'new', 'typeof', 'delete', 'null', 'undefined',
                                   'true', 'false', 'this', 'try', 'catch')))


def _hl(line):
    out = []
    pos = 0
    for m in _JS_TOKEN.finditer(line):
        out.append(html.escape(line[pos:m.start()]))
        if m.group(1):
            out.append('<span class="s">%s</span>' % html.escape(m.group(1)))
        elif m.group(2):
            out.append('<span class="c">%s</span>' % html.escape(m.group(2)))
        else:
            out.append('<span class="k">%s</span>' % html.escape(m.group(0)))
        pos = m.end()
    out.append(html.escape(line[pos:]))
    return ''.join(out)


def out_html(files, title, opts):
    """Self-contained browsable report."""
    nav = []
    sect = []
    for name, sections in files:
        anchor = re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-')
        nav.append('<a href="#%s">%s</a>' % (anchor, html.escape(name)))
        parts = ['<section id="%s"><h2>%s</h2>' % (anchor, html.escape(name))]
        if sections['module']:
            parts.append('<h3>module entry <span class="meta">%s</span></h3>'
                         % html.escape(sections['module']['sig']))
            parts.append('<pre>%s</pre>' % '\n'.join(
                _hl(l) for l in render_lines(sections['module']['lines']).split('\n')))
        for fn in sections['functions']:
            idx = fn['index']
            body = _hl(render_lines(fn['lines']))
            parts.append(
                '<details><summary>%s</summary><pre>%s</pre></details>'
                % (html.escape(str(fn['sig'])), body))
        parts.append('</section>')
        sect.append('\n'.join(parts))
    css = """
body{background:#12151c;color:#d7dde8;font:14px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;margin:0}
header{position:sticky;top:0;background:#0b0e14;border-bottom:1px solid #22293a;padding:12px 20px;z-index:9}
h1{font-size:16px;margin:0 0 6px;color:#8fd0ff}
h2{font-size:15px;color:#ffd479;border-top:1px solid #22293a;padding-top:14px;margin:26px 0 8px}
h3{font-size:13px;color:#9be08a;margin:14px 0 4px}
nav a{color:#7fb4ff;margin-right:12px;text-decoration:none;font-size:12px}
nav a:hover{text-decoration:underline}
pre{background:#0e1118;border:1px solid #1b2231;border-radius:6px;padding:10px 12px;overflow:auto;white-space:pre}
details>summary{cursor:pointer;color:#a8b6cc;padding:3px 0}
details[open]>summary{color:#ffd479}
.s{color:#a5e075}.c{color:#5f7188;font-style:italic}.k{color:#ff9ecb}
.meta{color:#5f7188;font-weight:400}
#q{background:#0b0e14;border:1px solid #2a3348;color:#d7dde8;padding:5px 8px;border-radius:5px;width:280px}
"""
    js = """
const q=document.getElementById('q');
q.addEventListener('input',()=>{const v=q.value.toLowerCase();
document.querySelectorAll('details').forEach(d=>{const t=d.querySelector('summary').textContent.toLowerCase();
d.style.display=(!v||t.includes(v))?'':'none';});});
"""
    return '\n'.join([
        '<!doctype html><html><head><meta charset="utf-8">',
        '<title>%s</title><style>%s</style></head><body>' % (html.escape(title), css),
        '<header><h1>%s</h1><nav>%s</nav><p><input id="q" placeholder="filter functions by name/signature"></p></header>'
        % (html.escape(title), ' '.join(nav)),
        '\n'.join(sect),
        '<script>%s</script></body></html>' % js,
    ])


def out_json(files, opts):
    data = []
    for name, sections in files:
        item = {'file': name, 'module': None, 'functions': []}
        if sections['module']:
            item['module'] = {'sig': sections['module']['sig'],
                              'code': render_lines(sections['module']['lines'])}
        for fn in sections['functions']:
            item['functions'].append({'index': fn['index'], 'name': fn['name'],
                                      'sig': fn['sig'], 'exact': fn['exact'],
                                      'code': render_lines(fn['lines'])})
        data.append(item)
    return json.dumps(data, ensure_ascii=False, indent=1)


# ----------------------------------------------------------------- commands
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


# --------------------------------------------------------------------- main
def build_parser():
    p = argparse.ArgumentParser(
        prog='veladec',
        description='QuickJS / Vela (.jsc, .rpk) static decompiler',
        epilog='examples:\n'
               '  veladec info app.rpk\n'
               '  veladec decompile app.rpk -o out/ --format js\n'
               '  veladec decompile app.rpk --format html -o out/\n'
               '  veladec disasm app.rpk --fn 42\n'
               '  veladec search app.rpk "activation"\n'
               '  veladec ls app.rpk --grep start\n',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--version', action='version', version='veladec ' + __version__)
    p.add_argument('--atom-base', type=int, default=ATOM_BASE_DEFAULT,
                   help='first atom-table index (default %(default)s)')
    p.add_argument('--table', default='auto',
                   help='opcode table: auto (default) or a release, e.g. 2020-11-08')
    p.add_argument('--builtins-file', help='JSON {id: name} of extra builtin atoms')
    p.add_argument('--indent', type=int, default=1, help=argparse.SUPPRESS)
    p.add_argument('-q', '--quiet', action='store_true')

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('-q', '--quiet', action='store_true')
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('info', help='fingerprint + per-file statistics', parents=[common])
    s.add_argument('target')
    s.set_defaults(func=cmd_info)

    s = sub.add_parser('unpack', help='extract .jsc files from an rpk', parents=[common])
    s.add_argument('target')
    s.add_argument('-o', '--out', default='veladec-unpack')
    s.set_defaults(func=cmd_unpack)

    s = sub.add_parser('ls', help='function index', parents=[common])
    s.add_argument('target')
    s.add_argument('--file')
    s.add_argument('--grep')
    s.set_defaults(func=cmd_ls)

    s = sub.add_parser('decompile', help='emit pseudo-JS (js/json/md/html)', parents=[common])
    s.add_argument('target')
    s.add_argument('-o', '--out')
    s.add_argument('--format', default='js', choices=('js', 'json', 'md', 'html'))
    s.add_argument('--file', help='only files whose name contains this')
    s.add_argument('--fn', type=int, help='only this function index')
    s.add_argument('--stdout', action='store_true')
    s.add_argument('--title', help='report title (html)')
    s.add_argument('--no-structure', action='store_true',
                   help='do not recover if/else blocks (pure goto form)')
    s.add_argument('--no-labels', action='store_true',
                   help='omit recovered label lines')
    s.add_argument('--offsets', action='store_true',
                   help='emit a signature comment per function')
    s.set_defaults(func=cmd_decompile)

    s = sub.add_parser('disasm', help='faithful instruction listing', parents=[common])
    s.add_argument('target')
    s.add_argument('-o', '--out')
    s.add_argument('--file')
    s.add_argument('--fn', type=int)
    s.add_argument('--name')
    s.add_argument('--stdout', action='store_true')
    s.set_defaults(func=cmd_disasm)

    s = sub.add_parser('strings', help='dump the atom (string) table', parents=[common])
    s.add_argument('target')
    s.add_argument('--grep')
    s.add_argument('--file')
    s.add_argument('--min', type=int, default=0)
    s.set_defaults(func=cmd_strings)

    s = sub.add_parser('search', help='regex search over all atoms', parents=[common])
    s.add_argument('target')
    s.add_argument('pattern')
    s.add_argument('--regex', action='store_true')
    s.set_defaults(func=cmd_search)

    s = sub.add_parser('selftest', help='validate decoding on the given input', parents=[common])
    s.add_argument('target')
    s.add_argument('--all-tables', action='store_true')
    s.set_defaults(func=cmd_selftest)

    s = sub.add_parser('tables', help='list embedded opcode tables', parents=[common])
    s.set_defaults(func=cmd_tables)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    opts = Opts(args)
    try:
        return args.func(args, opts)
    except FileNotFoundError as e:
        print('veladec: %s' % e, file=sys.stderr)
        return 2
    except (ValueError, KeyError, IndexError) as e:
        print('veladec: %s' % e, file=sys.stderr)
        return 2
