"""Title lookup only discovers candidates; it never verifies a citation."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
import hashlib
import json
import urllib.parse
import urllib.request
import urllib.error
import time
import threading
from .io import load, save, now
from .normalize import words
from .config import settings


def discover(run, workers=None):
    run = Path(run).resolve()
    config = settings()
    workers = workers or config["workers"]
    deadline = time.monotonic() + config["time_budget_seconds"]
    from .audit import audit
    audit(run)  # Deliver a complete provisional report before network discovery.
    manifest = load(run / "manifest.json")
    directory = run / "discovery"
    directory.mkdir(parents=True, exist_ok=True)
    references = [r for r in manifest["references"] if not r["fields"].get("arxiv_id")]
    lock = threading.Lock()
    next_request = [time.monotonic()]

    def lookup(ref):
        title = ref["fields"]["title"]
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode({"query.title": title, "rows": 3})
        result = {"ref_id": ref["id"], "source_url": url, "retrieved_at": now(), "candidates": []}
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "hallu-cite-checker/0.1 (citation candidate discovery)"})
            for attempt in range(config["max_attempts"]):
                with lock:
                    start = max(time.monotonic(), next_request[0])
                    next_request[0] = start + 0.4
                delay = start - time.monotonic()
                if delay > 0:
                    time.sleep(min(delay, max(0, deadline-time.monotonic())))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Discovery time budget exhausted; citation remains UNVERIFIED")
                try:
                    with urllib.request.urlopen(request, timeout=min(config["request_timeout"], remaining)) as response:
                        if urllib.parse.urlsplit(response.geturl()).hostname != "api.crossref.org":
                            raise ValueError("Redirect left the trusted metadata service")
                        raw = response.read(10_000_001)
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code not in {429, 502, 503, 504} or attempt + 1 == config["max_attempts"]:
                        raise
                    delay = exc.headers.get("Retry-After", "1")
                    delay = float(delay) if delay.replace(".", "", 1).isdigit() else 1
                    if delay >= deadline-time.monotonic() or delay > 10:
                        raise TimeoutError("Rate-limit retry exceeds budget; citation remains UNVERIFIED") from exc
                    time.sleep(max(0, delay))
            if len(raw) > 10_000_000:
                raise ValueError("Metadata response exceeded size limit")
            path = directory / (ref["id"] + ".json")
            path.write_bytes(raw)
            result.update(artifact=str(path.relative_to(run)), sha256=hashlib.sha256(raw).hexdigest())
            for item in json.loads(raw)["message"]["items"]:
                candidate = item.get("title", [""])[0]
                result["candidates"].append({"title": candidate, "doi": item.get("DOI"),
                    "authors": item.get("author", []), "venue": item.get("container-title", []),
                    "published": item.get("published", item.get("issued")), "pages": item.get("page"),
                    "title_similarity": round(SequenceMatcher(None, words(title), words(candidate)).ratio(), 4)})
        except Exception as exc:
            result["error"] = str(exc)
        return result

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(lookup, ref) for ref in references]
        for future in as_completed(futures):
            results.append(future.result())
            save(run / "discovery.json", {"schema_version": 1, "complete": len(results)==len(references),
                "note": "Candidates only; missing results never prove nonexistence.", "results": results})
            save(run / "progress.json", {"stage": "discovery", "completed": len(results), "total": len(references),
                "deadline_exhausted": time.monotonic() >= deadline, "updated_at": now()})
    save(run / "discovery.json", {"schema_version": 1, "note": "Candidates only; no verification or inferred nonexistence.", "results": results})
    return results
