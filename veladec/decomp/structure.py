"""Control-flow structuring: jump targets, spans, if/else and try/catch."""

from ..ins import resolve_label, JUMP_FMTS


class Line:
    """One emitted source line (indent depth + text), for txt/json/html output."""
    __slots__ = ('depth', 'text', 'pos')

    def __init__(self, depth, text, pos=None):
        self.depth = depth
        self.text = text
        self.pos = pos


class StructureMixin:
    """Span discovery and block structuring, mixed into FuncRenderer."""

    def _count_refs(self):
        refs = {}
        for i in self.ins:
            if i.fmt in JUMP_FMTS:
                t = resolve_label(self.ins, i.pos, i.extra[1], i.fmt)
                if t is not None:
                    refs[t] = refs.get(t, 0) + 1
        return refs

    def target(self, ins):
        if ins.fmt not in JUMP_FMTS:
            return None
        return resolve_label(self.ins, ins.pos, ins.extra[1], ins.fmt)

    def label(self, pos):
        return 'L%04x' % pos

    def _exc_name(self, pos):
        return 'exc' if self.handlers.get(pos) is None else 'exc%d' % self.handlers[pos]

    def _prev_ins(self, pos):
        prev = None
        for i in self.ins:
            if i.pos >= pos:
                break
            prev = i
        return prev

    def _find_spans(self):
        """Forward conditional jumps that can be rendered as if/else blocks."""
        spans = {}
        for i in self.ins:
            base, _ = self.d.normalize(i.name)
            if base not in ('if_true', 'if_false'):
                continue
            t = self.target(i)
            if t is None or t <= i.next:
                continue
            if self.refs.get(t, 0) != 1:
                continue
            prev = self._prev_ins(i.pos)
            if prev is not None and self.d.normalize(prev.name)[0] == 'dup':
                continue
            body_lo, body_hi = i.next, t
            if body_lo >= body_hi:
                continue
            spans[i.pos] = {'lo': body_lo, 'hi': body_hi, 'invert': base == 'if_true',
                            'else_lo': None, 'else_hi': None}
        # if/else: then-body ends with `goto L3` past the else block
        by_pos = {i.pos: i for i in self.ins}
        self.excvar = None
        self.nolabel = None
        self.loops = {}
        for i in self.ins:
            base, _ = self.d.normalize(i.name)
            if base != 'goto':
                continue
            t = self.target(i)
            if t is None or t >= i.pos:
                continue
            head = None
            for c in self.ins:
                if t <= c.pos < i.pos:
                    cb, _ = self.d.normalize(c.name)
                    if cb in ('if_true', 'if_false') and self.target(c) == i.next:
                        head = c
                        break
            if head is None:
                continue
            body_lo, body_hi = head.next, i.pos
            if body_lo >= body_hi:
                continue
            self.loops[t] = {'cond_pos': head.pos, 'cond_invert': None,
                             'body_lo': body_lo, 'body_hi': body_hi, 'end': i.next}
        self.handlers = {}
        for i in self.ins:
            base, _ = self.d.normalize(i.name)
            if base != 'catch':
                continue
            t = self.target(i)
            if t is not None and t > i.pos:
                self.handlers.setdefault(t, i.pos)
        self.suppressed = set()
        for start, sp in list(spans.items()):
            last = None
            for i in self.ins:
                if sp['lo'] <= i.pos < sp['hi']:
                    last = i
            if last is None:
                continue
            base, _ = self.d.normalize(last.name)
            if base != 'goto':
                continue
            t3 = self.target(last)
            if t3 is None or t3 <= sp['hi']:
                continue
            if self.refs.get(sp['hi'], 0) != 1:
                continue                      # else block shared with other jumps
            if not (sp['hi'] < t3 <= len(self.bc)):
                continue
            sp['else_lo'], sp['else_hi'] = sp['hi'], t3
            self.suppressed.add(last.pos)
        return spans

    def _is_block_boundary(self, pos):
        return any(sp['hi'] == pos or sp.get('else_hi') == pos
                   for sp in self.spans.values())

    def emit_label(self, pos, depth):
        tag = ''
        if self.refs.get(pos, 0) > 1:
            tag += '   // %d refs' % self.refs[pos]
        self.lines.append(Line(max(depth - 1, 0), self.label(pos) + ':' + tag))

    def catch_targets(self):
        out = set()
        for i in self.ins:
            base, _ = self.d.normalize(i.name)
            if base in ('catch', 'gosub'):
                t = self.target(i)
                if t is not None:
                    out.add(t)
        return out

    def _render_if(self, sp, depth):
        cond = self.pop()[0]
        if sp['invert']:
            test = cond[1:] if cond.startswith('!') else '!(%s)' % cond
        else:
            test = cond
        self.lines.append(Line(depth, 'if (%s) {' % test))
        self.render_range(sp['lo'], sp['hi'], depth + 1)
        if sp['else_lo'] is not None:
            self.lines.append(Line(depth, '} else {'))
            self.render_range(sp['else_lo'] + self._size_at(sp['else_lo']),
                              sp['else_hi'], depth + 1)
        self.lines.append(Line(depth, '}'))

    def _size_at(self, pos):
        for i in self.ins:
            if i.pos == pos:
                return i.size
        return 1
