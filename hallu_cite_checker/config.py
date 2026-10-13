"""Noninteractive configuration. This never changes host sandbox permissions."""
import os
from pathlib import Path
from .io import load, save

DEFAULTS = {"time_budget_seconds": 300, "request_timeout": 10,
            "max_attempts": 2, "workers": 1}


def config_path():
    return Path(os.environ.get("HALLU_CITE_CHECKER_CONFIG", str(Path.home() / ".config/hallu-cite-checker/config.json")))


def settings():
    path = config_path()
    return {**DEFAULTS, **(load(path) if path.exists() else {})}


def configure(output_root, **limits):
    if any(not isinstance(v, (int, float)) or v <= 0 for v in limits.values()):
        raise ValueError("All limits must be positive")
    if limits.get("workers", 1) > 3 or limits.get("max_attempts", 2) > 3:
        raise ValueError("At most three workers and attempts are allowed")
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    data = {**DEFAULTS, **limits, "output_root": str(root)}
    save(config_path(), data)
    return data


def new_run(input_path):
    from datetime import datetime
    import uuid
    data = settings()
    if not data.get("output_root"):
        raise ValueError("Run configure --output-root DIR once, or supply --out DIR")
    stem = Path(input_path).stem
    return Path(data["output_root"]) / (stem + "-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
