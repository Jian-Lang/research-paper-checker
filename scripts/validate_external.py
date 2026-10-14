#!/usr/bin/env python3
"""Validate a production distribution in temporary, isolated installation paths."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def run(argv, *, cwd, accepted=(0,)):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode not in accepted:
        raise RuntimeError(repr(argv) + '\n' + result.stdout[-6000:])
    return result


def validate(source):
    with tempfile.TemporaryDirectory(prefix='hallu-external-validation-') as directory:
        root = Path(directory)
        codex_home, output = root/'codex', root/'runs'
        run([sys.executable, source/'scripts/install_skill.py', '--codex-home', codex_home,
             '--runtime-root', root/'runtime', '--config', root/'config.json',
             '--output-root', output], cwd=root)
        skill = codex_home/'skills/research-paper-checker'
        info = json.loads((skill/'scripts/installation.json').read_text())
        prefix = info['command_prefix']
        if (skill/'scripts/tests').exists():
            raise RuntimeError('Production skill installed internal tests')
        run([*prefix, '--help'], cwd=root)
        for action in ('check', 'refine', 'preview', 'latex', 'audit', 'open-report'):
            run([*prefix, action, '--help'], cwd=root)
        run([*prefix, 'self-test'], cwd=root, accepted=(2,))
        project = root/'synthetic-input'
        project.mkdir()
        (project/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n'
                                      '\\cite{example}\n\\bibliography{references}\n\\end{document}\n')
        (project/'references.bib').write_text('@article{example, title={Synthetic validation entry}, '
                                            'author={Example, Alice}, year={2024}}\n')
        audit_run = output/'installation-smoke'
        run([*prefix, 'latex', project, '--out', audit_run], cwd=root)
        run([*prefix, 'confirm-coverage', audit_run, '--reviewer', 'release-validation',
             '--note', 'One generated synthetic entry; installation smoke only.'], cwd=root)
        run([*prefix, 'audit', audit_run], cwd=root, accepted=(1,))
        report = json.loads((audit_run/'report.json').read_text())
        if report['counts'] != {'VERIFIED': 0, 'REJECTED': 0, 'UNVERIFIED': 1}:
            raise RuntimeError('An entry without source evidence unexpectedly passed')
        for name in ('report.html', 'report.md', 'report.json'):
            if not (audit_run/name).is_file():
                raise RuntimeError('Missing output: ' + name)
        run([*prefix, 'write-json', audit_run, '--name', '../escape.json',
             '--payload-json', '{}'], cwd=root, accepted=(2,))
        run([*prefix, 'audit', root/'outside-output-root'], cwd=root, accepted=(2,))
        module = run([info['python'], '-I', '-c',
                      'import hallu_cite_checker; print(hallu_cite_checker.__file__)'], cwd=root)
        if not Path(module.stdout.strip()).is_relative_to(root/'runtime'):
            raise RuntimeError('Runtime imported the internal source checkout')
        print(json.dumps({'distribution': str(source), 'isolated_installation': True,
                          'internal_tests_installed': False, 'entry_help': True,
                          'actions_available': ['check', 'refine', 'preview', 'latex', 'audit', 'open-report'],
                          'no_evidence_entry': 'UNVERIFIED', 'reports_exported': ['HTML', 'Markdown', 'JSON'],
                          'path_guards': True, 'scoped_policy_checked': True,
                          'limitations': 'Installation and deterministic smoke validation; not a new full-paper accuracy test or a host approval UI test.'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    try:
        validate(args.source.resolve())
    except Exception as exc:
        sys.exit('VALIDATION ERROR: ' + str(exc))
