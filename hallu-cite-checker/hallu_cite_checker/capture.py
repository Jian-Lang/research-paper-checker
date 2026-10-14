"""Bounded reads from the source registry. No interactive approval mechanism."""
import urllib.request
import re
from pathlib import Path
from .evidence import trusted
from .io import save, now, sha256
from .config import settings


def capture(run, kind, url, name):
    if not trusted(kind, url):
        raise ValueError('URL is outside the configured citation source registry')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', name):
        raise ValueError('Artifact name must be a simple filename')
    directory = Path(run).resolve() / 'discovery'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    if path.exists():
        raise ValueError('Capture already exists; use a new name')
    event = {'source_url': url, 'kind': kind, 'retrieved_at': now()}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'hallu-cite-checker/0.1 (citation metadata verification)'})
        # Full official conference indices may exceed 10 MB. Metadata APIs
        # retain the small bound; only publisher index HTML gets 50 MB.
        limit = 50_000_000 if kind == 'official' else 10_000_000
        with urllib.request.urlopen(req, timeout=settings()['request_timeout']) as response:
            if not trusted(kind, response.geturl()):
                raise ValueError('Redirect left the trusted source registry')
            raw = response.read(limit + 1)
            event['final_url'] = response.geturl()
        if len(raw) > limit:
            raise ValueError('Source exceeds capture size limit')
        path.write_bytes(raw)
        event.update(artifact=str(path.relative_to(Path(run).resolve())), sha256=sha256(path), bytes=len(raw))
        if not raw:
            raise ValueError('Source returned an empty response; metadata is unavailable')
    except Exception as exc:
        event['error'] = str(exc)
    save(directory / (name + '.capture.json'), event)
    return event
