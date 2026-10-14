from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .io import load, save, fingerprint, now
from .inventory import inventory_latex, inventory_pdf
from .evidence import add_evidence, fetch_identifier
from .audit import audit


def main(argv=None):
    p = argparse.ArgumentParser(prog="hallu-cite-checker", description="Skill-driven citation metadata audit. Every unresolved item blocks PASS.")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser('refine', help='Resolve PDF formatting against saved evidence and try official fallbacks')
    s.add_argument('run')
    s = sub.add_parser('check', help='Extract PDF candidates, query live metadata, and write reports; coverage review remains required')
    s.add_argument('input')
    s.add_argument('--out')
    s = sub.add_parser('preview', help='Render original PDF pages for skill extraction review')
    s.add_argument('run')
    s.add_argument('--page', type=int, action='append', required=True)
    s = sub.add_parser('replay', help='Fresh PDF extraction and evidence replay; never a new online audit')
    s.add_argument('input')
    s.add_argument('--bundle', required=True)
    s.add_argument('--out')
    s = sub.add_parser('capture', help='Save an authentic response from a registered citation host')
    s.add_argument('run')
    s.add_argument('--kind', choices=('official','arxiv','crossref','datacite','google_scholar'), required=True)
    s.add_argument('--url', required=True)
    s.add_argument('--name', required=True)
    s = sub.add_parser('write-json', help='Write reviewed structured data inside one audit run')
    s.add_argument('run')
    s.add_argument('--name', required=True)
    s.add_argument('--payload-json', required=True)
    s = sub.add_parser('open-report', help='Open an already generated HTML report')
    s.add_argument('run')
    for mode in ("latex", "pdf"):
        s = sub.add_parser(mode, help="Build an unverified inventory; never auto-pass extraction")
        s.add_argument("input")
        s.add_argument("--out")
    s = sub.add_parser("configure", help="One-time noninteractive configuration; never changes Codex authorization")
    s.add_argument("--output-root", required=True)
    s.add_argument("--time-budget-seconds", type=float, default=300)
    s.add_argument("--request-timeout", type=float, default=10)
    s.add_argument("--max-attempts", type=int, default=2)
    s.add_argument("--workers", type=int, default=1)
    s = sub.add_parser("confirm-coverage", help="Record an explicit completed source reconciliation")
    s.add_argument("run")
    s.add_argument("--reviewer", required=True)
    s.add_argument("--note", required=True)
    s = sub.add_parser("add-evidence")
    s.add_argument("run")
    s.add_argument("ref_id")
    s.add_argument("artifact")
    s.add_argument("--kind", choices=("google_scholar", "official", "crossref", "arxiv", "datacite"), required=True)
    s.add_argument("--url", required=True)
    s.add_argument("--format", choices=("bibtex", "crossref", "arxiv", "datacite", "reviewed_metadata", "citation_html"), required=True)
    s.add_argument("--version-id", required=True)
    s.add_argument("--role", choices=("primary", "linked_version", "alternative_version"), default="primary")
    s.add_argument("--relation", default="")
    s.add_argument("--reviewer", default="")
    s.add_argument("--supporting-artifact")
    s = sub.add_parser("fetch")
    s.add_argument("run")
    s.add_argument("ref_id")
    s.add_argument("--kind", choices=("crossref", "arxiv"), required=True)
    s.add_argument("--id", required=True)
    s.add_argument("--role", choices=("primary", "linked_version", "alternative_version"), default="primary")
    s.add_argument("--relation", default="")
    s.add_argument("--reviewer", default="")
    s = sub.add_parser("discover", help="Discover Crossref title candidates; never auto-pass")
    s.add_argument("run")
    s = sub.add_parser("audit", help="Write reports; exit 0 PASS, 1 FAIL, 2 execution error")
    s.add_argument("run")
    s.add_argument("--no-write", action="store_true", help="Read-only audit, print full JSON to stdout")
    for child in sub.choices.values():
        child.allow_abbrev = False
    args = p.parse_args(argv)
    try:
        if args.command == 'refine':
            from .refinement import refine
            result = refine(args.run)
            print(json.dumps({'run':str(Path(args.run).resolve()),'counts':result['counts'],'blockers':result['blockers'],'verdict':result['verdict']}))
            return 0 if result['verdict']=='PASS' else 1
        if args.command == 'check':
            from .automatic import check_pdf
            from .config import new_run
            out = Path(args.out) if args.out else new_run(args.input)
            if out.exists():
                raise ValueError('Check output must be a fresh directory')
            result = check_pdf(args.input, out)
            print(json.dumps({'run':str(out.resolve()),'counts':result['counts'],'blockers':result['blockers'],'verdict':result['verdict']}))
            return 0 if result['verdict']=='PASS' else 1
        elif args.command == 'preview':
            import subprocess
            manifest = load(Path(args.run)/'manifest.json')
            source = manifest['inputs'][0]['path']
            directory = Path(args.run)/'preview'
            directory.mkdir(exist_ok=True)
            outputs = []
            for page in args.page:
                if not 1 <= page <= len(manifest.get('pages',[])):
                    raise ValueError('Preview page outside input PDF')
                target = directory/f'page-{page:03d}'
                try:
                    subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-scale-to','1800','-singlefile','-png',source,str(target)],check=True,capture_output=True)
                    outputs.append(str(target)+'.png')
                except subprocess.CalledProcessError:
                    if sys.platform != 'darwin':
                        raise
                    from pypdf import PdfReader, PdfWriter
                    writer = PdfWriter()
                    writer.add_page(PdfReader(source).pages[page-1])
                    selected = target.with_suffix('.pdf')
                    with selected.open('wb') as stream:
                        writer.write(stream)
                    subprocess.run(['qlmanage','-t','-s','1800','-o',str(directory),str(selected)],check=True,capture_output=True)
                    image = str(selected)+'.png'
                    if not Path(image).is_file():
                        raise ValueError('Native PDF preview produced no image')
                    outputs.append(image)
            print(json.dumps({'images':outputs}))
            return 0
        elif args.command == 'replay':
            from .config import new_run
            from .replay import replay_pdf
            out = Path(args.out) if args.out else new_run(args.input)
            result = replay_pdf(args.input, args.bundle, out)
            print(json.dumps({'run':str(out.resolve()),'counts':result['counts'],'verdict':result['verdict'],'mode':'captured_evidence_replay'}))
            return 0 if result['verdict']=='PASS' else 1
        elif args.command == 'capture':
            from .capture import capture
            event = capture(args.run,args.kind,args.url,args.name)
            print(json.dumps(event))
            return 2 if 'error' in event else 0
        elif args.command == 'write-json':
            import re
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json',args.name):
                raise ValueError('Name must be a simple JSON filename')
            data = json.loads(args.payload_json)
            if args.name == 'evidence.json':
                raise ValueError('Import evidence through add-evidence instead')
            save(Path(args.run).resolve()/args.name,data)
            print(json.dumps({'saved':args.name}))
        elif args.command == 'open-report':
            import subprocess
            target = Path(args.run).resolve()/'report.html'
            if not target.is_file():raise ValueError('HTML report is missing')
            subprocess.run(['open',str(target)],check=True)
        elif args.command in {"latex", "pdf"}:
            from .config import new_run
            out = Path(args.out) if args.out else new_run(args.input)
            if (out / "manifest.json").exists() or (out / "evidence.json").exists():
                raise ValueError("Output run exists; choose a new --out to preserve evidence")
            result = (inventory_latex if args.command == "latex" else inventory_pdf)(args.input, out)
            print(json.dumps({"run": str(out.resolve()), "references": len(result["references"]), "coverage": "NOT_CONFIRMED"}))
        elif args.command == "configure":
            from .config import configure
            print(json.dumps(configure(args.output_root, time_budget_seconds=args.time_budget_seconds,
                request_timeout=args.request_timeout, max_attempts=args.max_attempts, workers=args.workers)))
        elif args.command == "confirm-coverage":
            path = Path(args.run) / "manifest.json"
            manifest = load(path)
            if not manifest["references"] or manifest.get("issues"):
                raise ValueError("Cannot confirm empty inventory or unresolved extraction issues")
            if not args.reviewer.strip() or not args.note.strip():
                raise ValueError("Reviewer and note cannot be empty")
            manifest["coverage"] = {"reviewed": True, "reviewer": args.reviewer, "note": args.note,
                                    "reference_count": len(manifest["references"]),
                                    "reference_fingerprint": fingerprint(manifest["references"]), "reviewed_at": now()}
            save(path, manifest)
            print("Coverage attestation saved; metadata still requires verification.")
        elif args.command == "add-evidence":
            record = add_evidence(args.run, args.ref_id, args.artifact, args.kind, args.url, args.format,
                                  args.role, args.version_id, args.relation, args.reviewer, args.supporting_artifact)
            print(json.dumps({"ref_id": record["ref_id"], "artifact": record["artifact"]}))
        elif args.command == "discover":
            from .discover import discover
            results = discover(args.run)
            print(json.dumps({"references_queried": len(results), "errors": sum("error" in r for r in results)}))
        elif args.command == "fetch":
            record = fetch_identifier(args.run, args.ref_id, args.kind, args.id, args.role, args.relation, args.reviewer)
            print(json.dumps({"ref_id": record["ref_id"], "source_url": record["source_url"]}))
        else:
            report = audit(args.run, write_reports=not args.no_write)
            print(json.dumps(report if args.no_write else {"verdict": report["verdict"], "counts": report["counts"], "blockers": len(report["blockers"])}))
            return 0 if report["verdict"] == "PASS" else 1
        return 0
    except Exception as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
