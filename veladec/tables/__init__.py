"""QuickJS opcode / predefined-atom tables, one module per release.

Source: quickjs-opcode.h + quickjs-atom.h from official QuickJS releases
(https://bellard.org/quickjs/).  Regenerate with tools/gen_tables.py.

Each ``v<release>.py`` module exposes:

  ``K``      number of "pre" opcodes (short opcodes are numbered ``K + i``)
  ``PRE``    [(name, size, npop, npush, fmt), ...] -- the plain opcodes
  ``SHORT``  same shape -- the ``SHORT_OPCODES`` variants
  ``ATOMS``  predefined atom names, indexed by atom id
"""

from . import v2019_07_09
from . import v2019_12_21
from . import v2020_01_19
from . import v2020_07_05
from . import v2020_11_08
from . import v2021_03_27

_MODULES = {
    '2019-07-09': v2019_07_09,
    '2019-12-21': v2019_12_21,
    '2020-01-19': v2020_01_19,
    '2020-07-05': v2020_07_05,
    '2020-11-08': v2020_11_08,
    '2021-03-27': v2021_03_27,}

OPCODE_TABLES = {ver: {'K': m.K, 'pre': m.PRE, 'short': m.SHORT}
                 for ver, m in _MODULES.items()}

ATOM_TABLES = {ver: m.ATOMS for ver, m in _MODULES.items()}

RELEASES = tuple(_MODULES)
