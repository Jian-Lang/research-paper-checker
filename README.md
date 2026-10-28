# Research Paper Checker

A Codex skill for evidence-based citation metadata checks in PDF papers and LaTeX / Overleaf projects. The current subtool, **hallu-cite-checker**, checks titles, authors, years, venues and identifiers; it does not assess whether citations support claims.

## Structure

```text
research-paper-checker/
├── SKILL.md                     Parent skill entry
├── agents/                      Codex display metadata
├── references/                  Citation workflow and final review rules
├── scripts/
│   ├── install_skill.py         Installer
│   ├── run_checker.py           Fixed audit entry
│   └── hallu_cite_checker/      Python implementation of the citation subtool
├── pyproject.toml               Runtime dependencies and packaging
└── REPORTS/                    Generated reports (ignored by Git)
```

`hallu_cite_checker` is a Python package, not another skill. There is one skill entry at the repository root. Tests, sample papers, development utilities, local configuration and generated evidence are excluded from this distribution.

## Install

Requires Python 3.10+, Codex CLI and Poppler (`pdftotext` and `pdftoppm`).

```sh
git clone git@github.com:Jian-Lang/research-paper-checker.git
cd research-paper-checker
python3 scripts/install_skill.py
```

Installation creates an isolated runtime, installs the skill into `~/.codex/skills/research-paper-checker`, and configures `REPORTS/` as the default output directory. Use `--output-root /path/to/reports` to choose another location. The exact paths are saved in the installed skill's `scripts/installation.json`.

The installer saves a scoped Codex command rule. Restart Codex to load it; managed policy may override local rules. Audit actions use the fixed entry and do not request incremental permissions.

## Use and reports

Ask Codex:

> Use research-paper-checker to check the citations in /path/to/paper.pdf.

Each run creates `REPORTS/<paper-name>-<timestamp>-<id>/` containing:

- `report.html`: interactive final report, opened after final review.
- `report.md`: readable Markdown findings.
- `report.json`: detailed field comparisons and decisions.
- Evidence, extraction and review artifacts supporting the findings.

The skill reviews every bibliography entry and rechecks flagged results before final export. No separate model API is required. Automatic PDF extraction supports continuously numbered author-year bibliographies; other layouts require the skill's reviewed extraction workflow.

## Decisions

| Result | Meaning |
| --- | --- |
| Verified | Supplied metadata matches trusted evidence. |
| Rejected | A confirmed metadata conflict. |
| Unverified | Evidence, extraction or version remains unresolved. |

Actual Google Scholar citation exports, official publishers/proceedings, Crossref and arXiv are trusted. Every rejected or unverified entry blocks PASS. Missing optional source fields are disclosed; PASS is conditional on extraction and source accuracy.

[Skill instructions](SKILL.md) · [Citation workflow](references/hallu-cite-checker.md) · [Final review](references/final-review.md)
