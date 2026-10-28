# Research Paper Checker

A parent Codex skill that routes research paper checks to dedicated checkers. The current checker, **hallu-cite-checker**, audits citation titles, authors, years, venues and identifiers in PDF papers and LaTeX / Overleaf projects. It does not assess whether citations support claims.

## Structure

```text
research-paper-checker/
├── SKILL.md                         Parent entry and checker index
├── agents/                          Parent Codex display metadata
├── scripts/
│   └── install_skill.py             Shared installer
├── checkers/
│   └── hallu-cite-checker/
│       ├── SKILL.md                 Citation checker instructions
│       ├── references/              Citation workflow and final review rules
│       ├── scripts/
│       │   ├── run_checker.py       Fixed citation audit entry
│       │   └── hallu_cite_checker/  Citation checker Python package
│       └── pyproject.toml           Citation checker dependencies
└── REPORTS/                         Shared generated reports (ignored by Git)
```

The parent owns routing, installation and the shared report location. Each checker owns its instructions, references, implementation and dependencies. `hallu_cite_checker` is the citation checker's Python package. Tests, sample papers, development utilities, local configuration and generated evidence are excluded from this distribution.

## Install

Requires Python 3.10+, Codex CLI and Poppler (`pdftotext` and `pdftoppm`).

```sh
git clone git@github.com:Jian-Lang/research-paper-checker.git
cd research-paper-checker
python3 scripts/install_skill.py
```

Installation creates an isolated runtime, installs the parent and its `checkers/` subtree into `~/.codex/skills/research-paper-checker`, and configures the repository's `REPORTS/` as the default output directory. Use `--output-root /path/to/reports` to choose another location.

The citation checker's interpreter, fixed entry and output root are recorded in `~/.codex/skills/research-paper-checker/checkers/hallu-cite-checker/scripts/installation.json`. The installed layout mirrors this repository. Re-running the installer upgrades the former flat layout and removes its obsolete managed entry/configuration files; existing reports remain intact.

The installer saves a scoped Codex command rule. Restart Codex to load it; managed policy may override local rules. Audit actions use the fixed entry and do not request incremental permissions.

## Use and reports

Ask Codex:

> Use research-paper-checker to check the citations in /path/to/paper.pdf.

Each run creates `REPORTS/<paper-name>-<timestamp>-<id>/` containing:

- `report.html`: interactive final report, opened after final review.
- `report.md`: readable Markdown findings.
- `report.json`: detailed field comparisons and decisions.
- Evidence, extraction and review artifacts supporting the findings.

The parent reads its checker index and loads `checkers/hallu-cite-checker/SKILL.md` for citation requests. The checker reviews every bibliography entry and rechecks flagged results before final export. No separate model API is required. Automatic PDF extraction supports continuously numbered author-year bibliographies; other layouts require the checker's reviewed extraction workflow.

## Decisions

| Result | Meaning |
| --- | --- |
| Verified | Supplied metadata matches trusted evidence. |
| Rejected | A confirmed metadata conflict. |
| Unverified | Evidence, extraction or version remains unresolved. |

Actual Google Scholar citation exports, official publishers/proceedings, Crossref and arXiv are trusted. Every rejected or unverified entry blocks PASS. Missing optional source fields are disclosed; PASS is conditional on extraction and source accuracy.

[Parent / checker index](SKILL.md) · [Citation checker](checkers/hallu-cite-checker/SKILL.md) · [Citation workflow](checkers/hallu-cite-checker/references/hallu-cite-checker.md) · [Final review](checkers/hallu-cite-checker/references/final-review.md)
