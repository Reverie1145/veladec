"""Builtin-atom aliases: the same id means different things across Vela builds.

QuickJS atom ids below ``ATOM_BASE`` index the engine's *predefined* atom
table, which Vela has rebuilt more than once.  veladec pins the names it can
prove (``veladec/builtins.py``), but a handful stay ambiguous: id 66 is
``value`` in a 2.0.5 package and looked like ``state`` in an older one, id 103
is ``defineProperty`` in one and ``assign`` in the other.

Instead of guessing once and getting it wrong for half the packages, the
runtime resolves an ambiguous id against the receiver: the name that the
object actually implements wins, the choice is logged, and ``--atom ID=NAME``
overrides both.
"""

# id -> candidate names, most common first
ALIASES = {
    66: ('value', 'state'),
    93: ('join', 'with'),
    103: ('defineProperty', 'assign'),
    149: ('String', 'Array'),
    153: ('Math', 'Boolean'),
}

# id -> resolved name, filled in as the interpreter learns them
LEARNED = {}

# Why this table exists: in the 2.0.5 engine the method/property block of the
# predefined table sits three slots higher than upstream QuickJS, so upstream
# ``toString`` (54) arrives as id 57, ``value`` (63) as 66, ``defineProperty``
# (100) as 103.  veladec/builtins.py was pinned on an older build, so a name it
# reports can be off by that shift.  Rather than re-pin and break the old
# packages, the runtime offers the shifted name as a second candidate and lets
# the receiver decide: an object only answers the method it actually has.
_SHIFT = 3


def _build_alts():
    from ..builtins import BUILTINS
    from ..tables.v2020_11_08 import ATOMS
    out = {}
    for aid, name in BUILTINS.items():
        for cand in (aid - _SHIFT, aid + _SHIFT):
            if 0 <= cand < len(ATOMS):
                alt = ATOMS[cand]
                if alt and alt != name:
                    out.setdefault(name, [])
                    if alt not in out[name]:
                        out[name].append(alt)
    return out


NAME_ALTS = _build_alts()


def alts(name):
    """Candidate spellings for a builtin atom name, best guess first."""
    return NAME_ALTS.get(name, ())


def _shifted(atom_id):
    from ..tables.v2020_11_08 import ATOMS
    out = []
    for cand in (atom_id - _SHIFT, atom_id + _SHIFT):
        if 0 <= cand < len(ATOMS):
            out.append(ATOMS[cand])
    return out


def candidates(atom_id, override=None):
    """Names to try for an unresolved builtin atom id, best guess first."""
    out = []
    for name in ((override,) if override else ()) + tuple(ALIASES.get(atom_id, ())) \
            + ((LEARNED[atom_id],) if atom_id in LEARNED else ()) \
            + tuple(_shifted(atom_id)):
        if name and name not in out:
            out.append(name)
    return out


def learn(atom_id, name):
    LEARNED[atom_id] = name
