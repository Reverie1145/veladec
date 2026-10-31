"""Predefined (built-in) atom ids for Vela/aiot QuickJS builds.

Operands below ``ATOM_BASE`` index QuickJS' *predefined* atom table
(JS_ATOM_*), which is version dependent.  Vela's fork removed a number of
entries, so a single affine offset does NOT reproduce upstream names: the
values below were pinned one by one from usage evidence (see README, "atom
calibration").  Unknown ids are rendered as ``$kN``.

Evidence anchors
----------------
22  ``default``    interop helper body is ``return {default: a0}``; module
                   export lists ``('local', 0, 'default')``
27  ``object``     ``typeof x != "object"``
72  ``number``     73 ``boolean``  74 ``string``   (typeof comparisons)
95  ``split``      only ever appears as ``str <split> "..."``
110 ``source``     location object field
134 ``groups``     regexp match groups
145..156          Object..Function, in upstream order, offset by -1
154 ``JSON``       ``JSON.parse`` on a signed-token payload
164 ``Uint8Array`` ``new Uint8Array(n)``
"""

BUILTINS = {
    22: 'default',
    27: 'object',
    56: 'name',
    66: 'state',
    72: 'number',
    73: 'boolean',
    74: 'string',
    95: 'split',
    110: 'source',
    134: 'groups',
    145: 'Object',
    146: 'Array',
    147: 'Error',
    148: 'Number',
    149: 'String',
    150: 'Boolean',
    151: 'RegExp',
    152: 'Date?',      # unconfirmed
    153: 'Math',
    154: 'JSON',
    155: 'Date',
    156: 'Function',
    164: 'Uint8Array',
}
