"""Fetch the detector weights from their public source into a models folder and record what
was fetched in manifest.json. For building a worker image; never needed for app development.

    python scripts/fetch_models.py --models-dir /models --accept-model-terms

DO NOT RUN on the owner's Mac (no weight downloads there) and not before the licensing
decision in docs/MODEL_LICENSING_DECISION.md: the weights are AGPL-3.0 (or Ultralytics
Enterprise). It refuses to start without `--accept-model-terms`, which is the owner's
statement that fetching and using them for this purpose has been approved.

Nothing comes from a personal Drive or a Colab session: only the publisher's own release
URL, listed in aquatrack/analysis/pose/manifest.py. The file's size is checked against the
size the release reports; the release publishes no hash, so the SHA-256 is computed here
and pinned in the manifest. The pose model is exported separately
(scripts/export_rtmw_onnx.py) and added with `--add`.
"""

import argparse
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from aquatrack.analysis.pose import manifest


def fetch(source: manifest.ModelSource, dest: Path) -> dict:
    target = dest / source.name
    if not target.exists():
        request = urllib.request.Request(source.url, headers={"User-Agent": "aquatrack-build/1.0"})
        with urllib.request.urlopen(request, timeout=300) as response, target.open("wb") as out:
            while block := response.read(1 << 20):
                out.write(block)
    try:
        digest = manifest.check_download(target, source)
    except manifest.ModelError as e:
        target.unlink()
        raise SystemExit(e.message) from e
    size = target.stat().st_size
    return {"sha256": digest, "bytes": size, "source": source.url, "publisher": source.publisher}


def add_local(path: Path) -> dict:
    """Record a file that is already in the models folder (the exported pose model)."""
    return {
        "sha256": manifest.sha256_of(path),
        "bytes": path.stat().st_size,
        "source": "built in this image",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-dir", type=Path, required=True)
    parser.add_argument("--accept-model-terms", action="store_true")
    parser.add_argument("--add", action="append", default=[], help="a file already in the folder")
    parser.add_argument("--skip-fetch", action="store_true", help="only record --add files")
    args = parser.parse_args()
    if not args.accept_model_terms:
        print("Refusing to run: read docs/MODEL_LICENSING_DECISION.md first.", file=sys.stderr)
        return 2
    args.models_dir.mkdir(parents=True, exist_ok=True)
    files = manifest.load_manifest(args.models_dir) or {}
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    if not args.skip_fetch:
        files["yolo11m.pt"] = fetch(manifest.SOURCES["yolo11m.pt"], args.models_dir) | {
            "recorded_at": stamp
        }
    for name in args.add:
        files[name] = add_local(args.models_dir / name) | {"recorded_at": stamp}
    path = manifest.write_manifest(args.models_dir, files)
    for name, entry in sorted(files.items()):
        print(f"{name}  {entry['bytes']} bytes  sha256 {entry['sha256']}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
