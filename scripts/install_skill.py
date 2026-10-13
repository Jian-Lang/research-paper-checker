#!/usr/bin/env python3
"""One-time installation, scoped Codex rule, optional independent verification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import venv
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]


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
    shutil.copy2(PROJECT/'pyproject.toml', path/'pyproject.toml')
    shutil.copytree(PROJECT/'hallu_cite_checker', path/'hallu_cite_checker',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(PROJECT/'tests', path/'tests', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))


def build_runtime(root, source, log):
    python = root/'bin/python'
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(root)
    command([python, '-m', 'pip', '--disable-pip-version-check', 'install', '--no-input',
             str(source) + '[dev]'], cwd=source, log=log)
    return python


def copy_skill(target):
    source = PROJECT/'skill/research-paper-checker'
    for item in source.rglob('*'):
        if item.is_file() and '__pycache__' not in item.parts:
            destination = target/item.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
    tests = target/'scripts/tests'
    tests.mkdir(parents=True, exist_ok=True)
    for test in (PROJECT/'tests').glob('test_*.py'):
        shutil.copy2(test, tests/test.name)


def configure_installation(skill, python, output, config):
    config_data = {'output_root': str(output), 'time_budget_seconds': 300,
                   'request_timeout': 10, 'max_attempts': 2, 'workers': 1}
    write_json(config, config_data)
    entry = skill/'scripts/run_checker.py'
    info = {'python': str(python), 'entry': str(entry), 'config': str(config),
            'output_root': str(output), 'command_prefix': [str(python), '-I', str(entry)]}
    write_json(skill/'scripts/installation.json', info)
    return info


def policy_checks(rule, prefix, log):
    codex = shutil.which('codex')
    if not codex:
        raise RuntimeError('Codex CLI is required to validate the scoped permission rule')
    positive = command([codex, 'execpolicy', 'check', '--rules', rule, '--', *prefix, '--help'], log=log)
    negative = command([codex, 'execpolicy', 'check', '--rules', rule, '--', prefix[0],
                        '-c', 'print(1)'], log=log)
    return {'allowed_entry': json.loads(positive.stdout), 'arbitrary_python': json.loads(negative.stdout)}


def verify(pdf, bundle, output, installed, rule, policy, log):
    started = time.monotonic()
    clean = output/('independent-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    clean.mkdir()
    source = clean/'source'
    snapshot(source)
    python = build_runtime(clean/'runtime', source, log)
    skill = clean/'skill/research-paper-checker'
    copy_skill(skill)
    isolated = configure_installation(skill, python, clean/'runs', clean/'config.json')
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['TMPDIR'] = str(clean/'tmp')
    Path(env['TMPDIR']).mkdir()
    tests = command([python, '-B', '-m', 'unittest', 'discover', '-s', str(source/'tests'), '-v'],
                    cwd=clean, env=env, log=log)
    (clean/'tests.log').write_text(tests.stdout, encoding='utf-8')
    validator = Path.home()/'.codex/skills/.system/skill-creator/scripts/quick_validate.py'
    if validator.is_file():
        command([python, validator, skill], cwd=clean, env=env, log=log)
    copied_pdf = clean/'input.pdf'
    shutil.copy2(pdf, copied_pdf)
    # Only reviewed inventory and actual evidence; never copy old report/verdict.
    cached = clean/'captured-evidence'
    cached.mkdir()
    old_manifest = json.loads((bundle/'manifest.json').read_text())
    old_evidence = json.loads((bundle/'evidence.json').read_text())
    for name in ('manifest.json', 'evidence.json', 'annotations.json'):
        if (bundle/name).exists():
            shutil.copy2(bundle/name, cached/name)
    for record in old_evidence['records']:
        for key in ('artifact', 'supporting_artifact'):
            if record.get(key):
                relative = Path(record[key])
                if relative.is_absolute() or '..' in relative.parts:
                    raise RuntimeError('Evidence bundle path is not relative')
                dest = cached/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bundle/relative, dest)
    run = clean/'runs/verified-paper'
    prefix = isolated['command_prefix']
    command([*prefix, 'replay', copied_pdf, '--bundle', cached, '--out', run],
            cwd=clean, env=env, accepted=(0, 1), log=log)
    first = json.loads((run/'report.json').read_text())
    expected = {'VERIFIED': 44, 'REJECTED': 2, 'UNVERIFIED': 7}
    sample_hash = 'fb587dfee6fc0258f1af2db7d5374a6f46e706d17e29b63573bcefc20be8c48a'
    # Expectations are fixture-specific; other papers still require reviewed coverage.
    known_sample = hashlib.sha256(copied_pdf.read_bytes()).hexdigest() == sample_hash
    if first['blockers'] or (known_sample and (len(first['references']) != 53 or first['counts'] != expected)):
        raise RuntimeError('Sample regression changed unexpectedly: ' + repr(first['counts']))
    statuses = {r['id']: r['status'] for r in first['references']}
    if known_sample and statuses.get('smit2024') != 'UNVERIFIED':
        raise RuntimeError('Alternative-author-order regression failed')
    for _ in range(2):
        command([*prefix, 'audit', run], cwd=clean, env=env, accepted=(0, 1), log=log)
        repeated = json.loads((run/'report.json').read_text())
        if {r['id']: r['status'] for r in repeated['references']} != statuses:
            raise RuntimeError('Repeated decisions are not deterministic')
    # Installed, fixed entry is also exercised twice under this setup authorization.
    for _ in range(2):
        command([*installed['command_prefix'], 'audit', run], cwd=clean, env=env,
                accepted=(0, 1), log=log)
    for text in (('独立环境证据复跑', '真实记录存在版本差异') if known_sample else ('独立环境证据复跑',)):
        if text not in (run/'report.html').read_text(encoding='utf-8'):
            raise RuntimeError('Report is missing replay or author-order disclosure')
    events = []
    for name, url in (
        ('live-smit.html', 'https://proceedings.mlr.press/v235/smit24a.html'),
        ('live-goyal.html', 'https://proceedings.mlr.press/v97/goyal19a.html')):
        captured = command([*prefix, 'capture', run, '--kind', 'official', '--url', url, '--name', name],
                           cwd=clean, env=env, accepted=(0, 2), log=log)
        events.append(json.loads(captured.stdout))
    # Fail-closed integration tests: changed input and corrupt source must be refused.
    changed_pdf = clean/'changed.pdf'
    changed_pdf.write_bytes(copied_pdf.read_bytes() + b'\n% changed input\n')
    invalid = command([*prefix, 'replay', changed_pdf, '--bundle', cached, '--out', clean/'runs/changed'],
                      cwd=clean, env=env, accepted=(2,), log=log)
    refused = command([*prefix, 'write-json', run, '--name', '../escape.json', '--payload-json', '{}'],
                      cwd=clean, env=env, accepted=(2,), log=log)
    outside = command([*prefix, 'audit', cached], cwd=clean, env=env, accepted=(2,), log=log)
    corrupt_bundle = clean/'corrupted-evidence-test'
    shutil.copytree(cached, corrupt_bundle)
    mutable = next(r for r in old_evidence['records'] if r.get('artifact'))
    artifact = corrupt_bundle/mutable['artifact']
    artifact.write_bytes(artifact.read_bytes() + b'\nTAMPERED')
    corrupted = command([*prefix, 'replay', copied_pdf, '--bundle', corrupt_bundle,
                         '--out', clean/'runs/corrupt'], cwd=clean, env=env, accepted=(2,), log=log)
    opened = command([*installed['command_prefix'], 'open-report', run], cwd=clean, env=env, log=log)
    versions = command([python, '-I', '-m', 'pip', '--disable-pip-version-check', 'freeze'], log=log).stdout
    receipt = {'created_at': datetime.now(timezone.utc).isoformat(), 'independent_environment': str(clean),
               'source_project_used_at_runtime': False, 'old_reports_imported': False,
               'fresh_full_network_audit': False, 'reused_visual_review': True,
               'counts': first['counts'], 'references': len(first['references']),
               'pdf_sha256': hashlib.sha256(copied_pdf.read_bytes()).hexdigest(),
               'execution': first['execution'], 'tests_passed': tests.returncode == 0,
               'integration_rejections': {'changed_input': invalid.returncode,
                    'path_escape': refused.returncode, 'outside_output_root': outside.returncode,
                    'corrupt_evidence': corrupted.returncode},
               'repeated_audits': 4, 'runtime_prompts_inside_setup_process': 0,
               'live_source_captures': events, 'permission_rule': str(rule), 'policy_checks': policy,
               'permission_scope': 'Exact runtime Python -I installed entry only; restart Codex to load; managed policy can override. Child-process tests do not prove prompt behavior in a new Codex session.',
               'dependencies': versions.splitlines(), 'duration_seconds': round(time.monotonic()-started, 2),
               'html_opened': opened.returncode == 0, 'report_html': str(run/'report.html'),
               'report_md': str(run/'report.md')}
    write_json(clean/'validation.json', receipt)
    write_json(PROJECT/'audit-runs/latest-independent-validation.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', default=str(PROJECT/'audit-runs'))
    parser.add_argument('--verify-pdf', type=Path)
    parser.add_argument('--bundle', type=Path)
    args = parser.parse_args()
    if bool(args.verify_pdf) != bool(args.bundle):
        parser.error('--verify-pdf and --bundle must be supplied together')
    if not shutil.which('pdftotext'):
        raise RuntimeError('Install Poppler/pdftotext during setup first')
    output = Path(args.output_root).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtime_root = Path.home()/'.local/share/hallu-cite-checker'
    runtime_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    log = runtime_root/('install-' + stamp + '.log')
    source = runtime_root/('source-' + stamp)
    snapshot(source)
    python = build_runtime(runtime_root/'runtime', source, log)
    skill = Path.home()/'.codex/skills/research-paper-checker'
    copy_skill(skill)
    config = Path.home()/'.config/hallu-cite-checker/config.json'
    installed = configure_installation(skill, python, output, config)
    rule = Path.home()/'.codex/rules/hallu-cite-checker.rules'
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_text('# Installed hallu-cite-checker only; no arbitrary Python allowance.\n' +
                    'prefix_rule(pattern=' + json.dumps(installed['command_prefix']) +
                    ', decision="allow")\n', encoding='utf-8')
    checks = policy_checks(rule, installed['command_prefix'], log)
    if checks['allowed_entry'].get('decision') != 'allow' or checks['arbitrary_python'].get('decision') == 'allow':
        raise RuntimeError('Scoped permission-rule validation failed')
    print('INSTALLATION: ' + json.dumps(installed), flush=True)
    print('Restart Codex to load the saved rule. Managed restrictions may still override it.', flush=True)
    if args.verify_pdf:
        receipt = verify(args.verify_pdf.resolve(), args.bundle.resolve(), output, installed, rule, checks, log)
        print('VALIDATION: ' + json.dumps(receipt, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        sys.exit('INSTALLATION ERROR: ' + str(exc))
