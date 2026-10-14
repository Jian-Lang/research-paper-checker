#!/usr/bin/env python3
"""Clone the internal repository and prepare a standalone, test-free release."""
import argparse
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def command(*argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def production_installer(path):
    tree = ast.parse(path.read_text())
    # The external installer contains setup only, without sample regression data.
    tree.body = [node for node in tree.body
                 if not isinstance(node, ast.FunctionDef) or node.name != 'verify']
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name == 'snapshot':
            node.body = [stmt for stmt in node.body if "PROJECT / 'tests'" not in ast.unparse(stmt)]
        elif node.name == 'build_runtime':
            class RemoveDev(ast.NodeTransformer):
                def visit_BinOp(self, expr):
                    if isinstance(expr.op, ast.Add) and isinstance(expr.right, ast.Constant) and expr.right.value == '[dev]':
                        return expr.left
                    return self.generic_visit(expr)
            RemoveDev().visit(node)
        elif node.name == 'copy_skill':
            node.body = node.body[:2]
        elif node.name == 'main':
            node.body = [stmt for stmt in node.body
                         if not any(token in ast.unparse(stmt)
                                    for token in ('--verify-pdf', '--bundle', 'args.verify_pdf', 'args.bundle'))]
    tree.body[0] = ast.Expr(value=ast.Constant(value='One-time skill installation and scoped Codex command rule.'))
    ast.fix_missing_locations(tree)
    path.write_text('#!/usr/bin/env python3\n' + ast.unparse(tree) + '\n')


def production_entry(path):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'main':
            node.body = [stmt for stmt in node.body
                         if not isinstance(stmt, ast.If) or "argv[0] == 'self-test'" not in ast.unparse(stmt.test)]
    ast.fix_missing_locations(tree)
    path.write_text('#!/usr/bin/env python3\n' + ast.unparse(tree) + '\n')


def prepare(source, destination, repository):
    if destination.exists():
        raise ValueError('Release destination already exists; choose a fresh directory')
    command('git', 'clone', '--no-hardlinks', str(source), str(destination))
    revision = command('git', 'rev-parse', 'HEAD', cwd=destination)
    # Start clean history so excluded internal fixtures cannot be recovered from Git.
    shutil.rmtree(destination/'.git')
    for relative in ('tests', 'skill/research-paper-checker/scripts/tests'):
        shutil.rmtree(destination/relative)
    for name in ('prepare_external.py', 'validate_external.py'):
        (destination/'scripts'/name).unlink(missing_ok=True)
    production_installer(destination/'scripts/install_skill.py')
    production_entry(destination/'skill/research-paper-checker/scripts/run_checker.py')
    project = destination/'pyproject.toml'
    project.write_text(re.sub(r'\n\[project.optional-dependencies\]\n.*?(?=\n\[)', '',
                              project.read_text(), flags=re.S))
    skill = destination/'skill/research-paper-checker/SKILL.md'
    skill.write_text(skill.read_text().replace(
        ' `self-test` runs the installed regression suite through this same authorized entry.', ''))
    readme = destination/'README.md'
    readme.write_text(readme.read_text().replace(
        'Requires Python 3.10+, Codex CLI and Poppler.',
        'Requires macOS, Python 3.10+, Codex CLI and Poppler.').replace(
        'git clone git@github.com:Jian-Lang/research-paper-checker.git\ncd research-paper-checker',
        f'git clone https://github.com/{repository}.git\ncd {repository.split("/")[-1]}').replace(
        'Input papers, reports and machine-specific configuration stay outside Git.',
        'This distribution contains runtime code and the installable skill. Internal tests, sample papers, audit reports and machine-specific configuration are excluded.'))
    metadata = {'distribution': 'external', 'internal_revision': revision,
                'included': ['runtime', 'skill', 'installer'],
                'excluded': ['tests', 'sample papers', 'audit runs', 'local configuration']}
    (destination/'release.json').write_text(json.dumps(metadata, indent=2) + '\n')
    excluded = [p for p in destination.rglob('*') if p.is_file() and (
        'tests' in p.parts or 'audit-runs' in p.parts or '__pycache__' in p.parts or
        p.suffix.lower() in {'.pdf', '.png', '.pyc'} or p.name == 'installation.json')]
    if excluded:
        raise ValueError('Internal artifacts found in release: ' + str(excluded))
    for path in destination.rglob('*.py'):
        ast.parse(path.read_text())
    command('git', 'init', '-b', 'main', cwd=destination)
    for setting in ('user.name', 'user.email'):
        identity = command('git', 'config', '--get', setting, cwd=Path(__file__).resolve().parents[1])
        command('git', 'config', setting, identity, cwd=destination)
    command('git', 'add', '.', cwd=destination)
    command('git', 'diff', '--cached', '--check', cwd=destination)
    print(json.dumps({'directory': str(destination), 'internal_revision': revision,
                      'files': len(command('git', 'ls-files', cwd=destination).splitlines())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--repository', default='Jian-Lang/research-paper-checker-external')
    args = parser.parse_args()
    try:
        prepare(args.source, args.destination.expanduser().resolve(), args.repository)
    except Exception as exc:
        sys.exit('RELEASE ERROR: ' + str(exc))
