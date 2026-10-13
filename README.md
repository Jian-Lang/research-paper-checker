# Research Paper Checker

Evidence-based citation checks for PDF papers and LaTeX / Overleaf projects.

**hallu-cite-checker** checks reference metadata: titles, authors, years, venues, identifiers and supplied bibliographic fields. It does not evaluate whether a citation supports a claim.

## Install

Requires Python 3.10+, Codex CLI and Poppler.

```sh
git clone git@github.com:Jian-Lang/research-paper-checker.git
cd research-paper-checker
python3 scripts/install_skill.py
```

Installation sets up the runtime, skill, output directory and a scoped Codex command rule. Restart Codex once to load the rule. All audit actions use that authorized entry; the tool never requests additional permissions during a run. Managed policy can override local rules.

## Use

In Codex:

> Use research-paper-checker to check the citations in /path/to/paper.pdf.

The skill checks every reference, reviews bibliography coverage, and opens the HTML report. Each run also exports Markdown and JSON with source evidence.

PDF automation currently supports continuously numbered author-year bibliographies. Other PDF layouts and LaTeX projects use the skill's reviewed extraction workflow.

## Decisions

| Result | Meaning |
| --- | --- |
| Verified | Metadata matches trusted evidence. |
| Rejected | A confirmed metadata conflict. |
| Unverified | Evidence or extraction remains incomplete. |

Actual Google Scholar citation exports, official publishers, proceedings, Crossref and arXiv are trusted sources. Conference claims require the corresponding published or accepted version. PDF formatting is resolved from original line breaks and source evidence.

Every rejected or unverified entry blocks a pass. Missing optional source fields are disclosed. No result is a universal guarantee of correctness.

[Skill instructions](skill/research-paper-checker/SKILL.md) · [Workflow](skill/research-paper-checker/references/hallu-cite-checker.md)

Input papers, reports and machine-specific configuration stay outside Git.
