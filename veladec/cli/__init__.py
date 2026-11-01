"""veladec command line interface."""

import argparse
import sys

from .. import __version__
from ..ser import ATOM_BASE_DEFAULT
from .commands import (cmd_info, cmd_ls, cmd_search, cmd_selftest, cmd_strings,


                       cmd_tables, cmd_unpack)
from .decompile_cmd import cmd_decompile, cmd_disasm
from .mv_cmd import cmd_mv
from .run_cmd import cmd_run
from .options import Opts


def build_parser():
    p = argparse.ArgumentParser(
        prog='veladec',
        description='QuickJS / Vela (.jsc, .rpk) static decompiler',
        epilog='examples:\n'
               '  veladec info app.rpk\n'
               '  veladec decompile app.rpk -o out/ --format js\n'
               '  veladec decompile app.rpk --format html -o out/\n'
               '  veladec mv app.rpk --stdout\n'
               '  veladec mv app.rpk --fn 42\n'
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

    s = sub.add_parser('mv', help='module / view map: entry, methods, closures, xrefs',
                       parents=[common])
    s.add_argument('target')
    s.add_argument('-o', '--out', help='write one .mv.<ext> per .jsc into this directory')
    s.add_argument('--format', default='text', choices=('text', 'json', 'md'))
    s.add_argument('--file', help='only files whose name contains this')
    s.add_argument('--fn', type=int, help='detail view for one function index')
    s.add_argument('--grep', help='only name-index rows whose name contains this')
    s.add_argument('--names', type=int, default=40,
                   help='max name-index rows per file (default %(default)s)')
    s.add_argument('--stdout', action='store_true', help='force stdout even with -o')
    s.set_defaults(func=cmd_mv)

    run = sub.add_parser('run', help='dynamic analysis: execute a function',
                         parents=[common],
                         description='Execute one bytecode function against stubbed '
                                     'platform APIs and report value, calls, watches.')
    run.add_argument('target')
    run.add_argument('--file', help='only files whose name contains this')
    run.add_argument('--fn', type=int, help='function index to run')
    run.add_argument('--method', help='run the function bound to this method name')
    run.add_argument('--args', help='JSON array of arguments, e.g. ["ABC"]')
    run.add_argument('--this', help='JSON value to use as `this`')
    run.add_argument('--null-this', action='store_true', help='pass null as this')
    run.add_argument('--global', dest='global_', action='append', metavar='NAME=JSON',
                     help='define a global (repeatable)')
    run.add_argument('--storage', action='append', metavar='KEY=VALUE',
                     help='seed storage (repeatable)')
    run.add_argument('--device-id', default='VELADEC-DEVICE-0001')
    run.add_argument('--now', type=int, default=1700000000000, help='Date.now() value')
    run.add_argument('--seed', type=int, default=0x2F6E2B1, help='Math.random seed')
    run.add_argument('--max-steps', type=int, default=5000000)
    run.add_argument('--trace', action='store_true', help='per-instruction trace')
    run.add_argument('--trace-calls', action='store_true', help='log every call')
    run.add_argument('--watch', action='append', metavar='NAME',
                     help='log reads/writes of a property (repeatable)')
    run.add_argument('--watch-call', type=int, action='append', metavar='FN',
                     help='log calls to fn[N] with args and result (repeatable)')
    run.add_argument('--stop-at', metavar='HEX[:N]',
                     help='breakpoint offset; :N breaks on the Nth hit')
    run.add_argument('--snap', action='append', metavar='HEX[:N]',
                     help='record locals at an offset without stopping (repeatable)')
    run.add_argument('--then', action='append', metavar='FN[:ARGS]',
                     help='call a closure the entry created, e.g. --then 23:["B82TTQG0"] '
                          '(repeatable, runs in order)')
    run.add_argument('--then-args', metavar='JSON', help='arguments for --then')
    run.add_argument('--then-this', metavar='JSON', help='this for --then')
    run.add_argument('--fill', choices=['undefined', 'require', 'noop'],
                     default='undefined',
                     help='value for arguments the caller did not supply '
                          '(module factories need require)')
    run.add_argument('--atom', action='append', metavar='ID=NAME',
                     help='force a builtin atom name (repeatable), e.g. --atom 103=assign')
    run.add_argument('--dump', action='store_true', help='dump frame at break/end')
    run.add_argument('--json', action='store_true', help='machine-readable output')
    run.set_defaults(func=cmd_run)

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
