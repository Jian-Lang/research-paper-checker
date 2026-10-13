#!/usr/bin/env python3
"""Fixed skill entry; invoke with the installed interpreter and -I."""
import json
import os
from pathlib import Path
import sys


def within_output(path, root):
    resolved = Path(path).expanduser().resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError('Run directory must be below the configured output root')
    return resolved


def main():
    installation = Path(__file__).with_name('installation.json')
    if not installation.is_file():
        raise ValueError('Run scripts/install_skill.py once before using the skill')
    installed = json.loads(installation.read_text(encoding='utf-8'))
    os.environ['HALLU_CITE_CHECKER_CONFIG'] = installed['config']
    from hallu_cite_checker.config import settings
    root = Path(settings()['output_root']).resolve()
    argv = sys.argv[1:]
    if not argv or argv[0] in ('-h', '--help'):
        from hallu_cite_checker.cli import main as cli
        return cli(argv)
    if argv[0] == 'self-test':
        import subprocess
        if len(argv) != 1:
            raise ValueError('self-test takes no arbitrary arguments')
        return subprocess.call([sys.executable,'-I','-B','-m','unittest','discover','-s',
                                str(Path(__file__).with_name('tests')),'-v'], cwd=root)
    allowed = {'pdf', 'latex', 'replay', 'check', 'refine', 'preview', 'capture', 'write-json', 'open-report',
               'confirm-coverage', 'add-evidence', 'fetch', 'discover', 'audit'}
    command = argv[0]
    if command not in allowed:
        raise ValueError('Unsupported installed-skill action')
    if len(argv) > 1 and argv[1] not in ('-h', '--help'):
        if command not in {'pdf', 'latex', 'replay', 'check'}:
            within_output(argv[1], root)
        if '--out' in argv:
            within_output(argv[argv.index('--out') + 1], root)
        for arg in argv:
            if arg.startswith('--out='):
                within_output(arg.partition('=')[2], root)
    from hallu_cite_checker.cli import main as cli
    return cli(argv)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(2)
