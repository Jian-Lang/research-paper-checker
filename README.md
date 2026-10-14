# Research Paper Checker

A modular project for checking research papers.

**Available now: hallu-cite-checker**, a citation metadata checker for PDF papers and LaTeX / Overleaf projects. It compares reference titles, authors, years, venues and identifiers with trusted sources. It does not assess whether citations support claims.

## Project

```text
research-paper-checker/
└── hallu-cite-checker/
    ├── hallu_cite_checker/  Runtime
    ├── skill/              Codex skill
    └── scripts/            Installer
```

All current checker files live in `hallu-cite-checker/`. Additional checking modules are planned; they are not implemented yet.

## Get Started

Requires macOS, Python 3.10+, Codex CLI and Poppler.

```sh
git clone https://github.com/Jian-Lang/research-paper-checker.git
cd research-paper-checker/hallu-cite-checker
python3 scripts/install_skill.py
```

Restart Codex after the one-time setup, then ask:

> Use research-paper-checker to check the citations in /path/to/paper.pdf.

Each audit exports HTML, Markdown and JSON. Incomplete evidence blocks a pass; no result guarantees universal accuracy. Managed Codex policies may override the installed command rule.

[Checker guide](hallu-cite-checker/README.md) · [Skill](hallu-cite-checker/skill/research-paper-checker/SKILL.md)

This external distribution excludes internal tests, sample papers, audit reports and local configuration.
