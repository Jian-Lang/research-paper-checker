#!/usr/bin/env python3
"""Install the parent skill, its citation checker and scoped Codex entry."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import venv
from datetime import datetime

PROJECT = Path(__file__).resolve().parents[1]
CHECKER_RELATIVE = Path('checkers/hallu-cite-checker')
CHECKER = PROJECT/CHECKER_RELATIVE


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def command(argv, *, cwd=None, env=None, accepted=(0,), log=None):
    print('STEP: ' + ' '.join(map(str, argv[:4])), flush=True)
    result = subprocess.run(list(map(str, argv)), cwd=cwd, env=env,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log:
        with log.open('a', encoding='utf-8') as stream:
            stream.write('COMMAND: ' + repr(list(map(str, argv))) + '\n' + result.stdout + '\n')
    if result.returncode not in accepted:
        raise RuntimeError('Command failed (' + str(result.returncode) + '): ' + result.stdout[-6000:])
    return result


def snapshot(path):
    path.mkdir(parents=True)
    shutil.copy2(CHECKER/'pyproject.toml', path/'pyproject.toml')
    shutil.copytree(CHECKER/'scripts/hallu_cite_checker', path/'scripts/hallu_cite_checker',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))


def build_runtime(root, source, log):
    python = root/'bin/python'
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(root)
    command([python, '-m', 'pip', '--disable-pip-version-check', 'install', '--no-input',
             str(source)], cwd=source, log=log)
    return python


def copy_skill(target):
    for name in ('SKILL.md', 'agents', 'scripts', 'checkers'):
        source = PROJECT/name
        destination = target/name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'installation.json'))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    # Retire only managed files from the former flat installation. Keep user
    # files and reports intact; the active checker now lives under checkers/.
    for relative in ('scripts/tests', 'scripts/hallu_cite_checker'):
        shutil.rmtree(target/relative, ignore_errors=True)
    for relative in ('scripts/run_checker.py', 'scripts/installation.json',
                     'references/hallu-cite-checker.md', 'references/final-review.md',
                     'pyproject.toml'):
        (target/relative).unlink(missing_ok=True)
    legacy_references = target/'references'
    if legacy_references.is_dir() and not any(legacy_references.iterdir()):
        legacy_references.rmdir()


def configure_installation(skill, python, output, config):
    config_data = {'output_root': str(output), 'time_budget_seconds': 300,
                   'request_timeout': 10, 'max_attempts': 2, 'workers': 1}
    write_json(config, config_data)
    checker = skill/CHECKER_RELATIVE
    entry = checker/'scripts/run_checker.py'
    info = {'python': str(python), 'entry': str(entry), 'config': str(config),
            'output_root': str(output), 'command_prefix': [str(python), '-I', str(entry)]}
    write_json(checker/'scripts/installation.json', info)
    return info


def policy_checks(rule, prefix, log):
    codex = shutil.which('codex')
    if not codex:
        raise RuntimeError('Codex CLI is required to validate the scoped permission rule')
    positive = command([codex, 'execpolicy', 'check', '--rules', rule, '--', *prefix, '--help'], log=log)
    negative = command([codex, 'execpolicy', 'check', '--rules', rule, '--', prefix[0],
                        '-c', 'print(1)'], log=log)
    return {'allowed_entry': json.loads(positive.stdout), 'arbitrary_python': json.loads(negative.stdout)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', default=str(PROJECT/'REPORTS'))
    parser.add_argument('--codex-home', type=Path, default=Path.home()/'.codex')
    parser.add_argument('--runtime-root', type=Path,
                        default=Path.home()/'.local/share/hallu-cite-checker')
    parser.add_argument('--config', type=Path,
                        default=Path.home()/'.config/hallu-cite-checker/config.json')
    args = parser.parse_args()
    if not all(shutil.which(tool) for tool in ('pdftotext', 'pdftoppm')):
        raise RuntimeError('Install Poppler (pdftotext and pdftoppm) during setup first')
    output = Path(args.output_root).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtime_root = args.runtime_root.expanduser().resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    log = runtime_root/('install-' + stamp + '.log')
    source = runtime_root/('source-' + stamp)
    snapshot(source)
    python = build_runtime(runtime_root/'runtime', source, log)
    codex_home = args.codex_home.expanduser().resolve()
    skill = codex_home/'skills/research-paper-checker'
    copy_skill(skill)
    config = args.config.expanduser().resolve()
    installed = configure_installation(skill, python, output, config)
    rule = codex_home/'rules/hallu-cite-checker.rules'
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_text('# Installed hallu-cite-checker only; no arbitrary Python allowance.\n' +
                    'prefix_rule(pattern=' + json.dumps(installed['command_prefix']) +
                    ', decision="allow")\n', encoding='utf-8')
    checks = policy_checks(rule, installed['command_prefix'], log)
    if checks['allowed_entry'].get('decision') != 'allow' or checks['arbitrary_python'].get('decision') == 'allow':
        raise RuntimeError('Scoped permission-rule validation failed')
    print('INSTALLATION: ' + json.dumps(installed), flush=True)
    print('Restart Codex to load the saved rule. Managed restrictions may still override it.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        sys.exit('INSTALLATION ERROR: ' + str(exc))
