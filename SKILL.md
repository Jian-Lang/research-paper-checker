---
name: research-paper-checker
description: Route research paper checks to the appropriate checker. Currently supports citation metadata audits in PDF papers and LaTeX/Overleaf projects, including fabricated references, hallucinated citations, BibTeX correctness and 幻觉引用检查. Does not assess whether citations support claims.
---

# Research Paper Checker

Select the checker below, then read its `SKILL.md` before executing its workflow. Checker paths are relative to this parent skill directory, both in the repository and after installation.

## Checker index

| Request | Checker | Instructions |
| --- | --- | --- |
| Citation metadata, bibliography, BibTeX or hallucinated-reference checks in PDF / LaTeX | hallu-cite-checker | [Citation checker](checkers/hallu-cite-checker/SKILL.md) |

Only the listed checker is implemented. For requests outside its scope, explain the available capability rather than treating a citation audit as another type of paper review.

## Installation and reports

Install from the repository with `python3 scripts/install_skill.py`. The installer copies this parent skill and its `checkers/` subtree together, installs checker dependencies, and configures each fixed executable entry.

For hallu-cite-checker, read `checkers/hallu-cite-checker/scripts/installation.json` for the installed interpreter, entry and output root. Follow the child skill's execution and evidence rules; do not infer executable paths from the current working directory.

The shared default report directory is the repository's `REPORTS/`. Each run gets its own subdirectory containing reports and supporting artifacts. Respect an explicitly configured output root and keep submitted papers unchanged. Report generated paths and the checker's final validation coverage.
