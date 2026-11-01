"""Output formats: plain JS, markdown, JSON and a self-contained HTML report."""

import html
import json
import re

from .. import __version__
from .asm import render_lines


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
