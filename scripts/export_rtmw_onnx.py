"""Export the public RTMW-x checkpoint to the ONNX file the worker loads.

    python scripts/export_rtmw_onnx.py --out /models/rtmw_x_stock.onnx --accept-model-terms

For a worker image build stage only. DO NOT RUN on the owner's Mac (it downloads a
checkpoint of about 370 MB) and not before the licensing decision in
docs/MODEL_LICENSING_DECISION.md.

It needs the export tool chain, which the worker itself does not: torch, mmengine 0.10.7,
mmcv-lite 2.1.0, mmpose 1.3.2, mmdet 3.3.0, onnx (the versions the Phase 1 export used; see
worker/Dockerfile). The steps are the ones used for the Phase 1 reference export:

1. download the checkpoint from OpenMMLab's own download host and check its size, the MD5
   that host reports, and that its SHA-256 starts with the eight characters in its name;
2. apply two small compatibility patches to the installed mmpose (the same two the Phase 1
   export needed): an optional import that needs the full mmcv, and a changed albumentations
   module path. They touch import plumbing only, not the model;
3. build the model from mmpose's own cocktail14 384x288 config, with SyncBN replaced by BN;
4. export backbone + head with outputs named simcc_x and simcc_y, opset 17;
5. check the result against the contract the estimator relies on.

Exports are not bit-for-bit reproducible: the hash of the file made here will differ from
the Phase 1 export (5ff227bf...). That is expected; what must hold is the input and output
contract here and the comparison with the reference pose in the acceptance test.

Run with --self-check to verify this script's own configuration without any download.
"""
# ruff: noqa: E501

import argparse
import importlib.util
import sys
import urllib.request
from pathlib import Path

from aquatrack.analysis.pose import manifest

CHECKPOINT = manifest.SOURCES["rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth"]
CONFIG = "wholebody_2d_keypoint/rtmpose/cocktail14/rtmw-x_8xb320-270e_cocktail14-384x288.py"
INPUT_SHAPE = (1, 3, 384, 288)  # N, C, H, W: the 384x288 checkpoint
OUTPUT_NAMES = ["simcc_x", "simcc_y"]
OPSET = 17

# (file inside the installed mmpose package, text to find, replacement)
PATCHES = [
    (
        "models/heads/__init__.py",
        "\nfrom .transformer_heads import EDPoseHead\n",
        "\ntry:\n    from .transformer_heads import EDPoseHead\nexcept ImportError:\n    EDPoseHead = None\n",
    ),
    (
        "datasets/transforms/common_transforms.py",
        "albumentations.augmentations.transforms, obj_type)",
        "albumentations, obj_type)",
    ),
]


def patch_mmpose(root: Path) -> list[str]:
    """Apply the import patches to an installed mmpose. Safe to run twice."""
    done = []
    for relative, old, new in PATCHES:
        path = root / relative
        text = path.read_text()
        if old in text:
            path.write_text(text.replace(old, new))
            done.append(relative)
    return done


def self_check() -> dict:
    """What can be verified about this script without downloading or importing mmpose."""
    contract = manifest.OnnxContract()
    assert contract.input_shape == INPUT_SHAPE, "export shape and worker contract disagree"
    assert [name for name, _ in contract.outputs] == OUTPUT_NAMES, "output names disagree"
    assert CHECKPOINT.url.startswith("https://download.openmmlab.com/"), "not the official host"
    assert CHECKPOINT.sha256_prefix in CHECKPOINT.name, "hash prefix is not the one in the name"
    assert "384x288" in CONFIG and "cocktail14" in CONFIG and "rtmw-x" in CONFIG
    return {
        "checkpoint": CHECKPOINT.name,
        "bytes": CHECKPOINT.bytes,
        "config": CONFIG,
        "input": INPUT_SHAPE,
        "outputs": OUTPUT_NAMES,
        "opset": OPSET,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--work", type=Path, default=Path("/tmp/rtmw-export"))
    parser.add_argument("--accept-model-terms", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        print("self-check ok:", self_check())
        return 0
    if not args.accept_model_terms:
        print("Refusing to run: read docs/MODEL_LICENSING_DECISION.md first.", file=sys.stderr)
        return 2
    if args.out is None:
        parser.error("--out is required")
    self_check()

    args.work.mkdir(parents=True, exist_ok=True)
    pth = args.work / CHECKPOINT.name
    if not pth.exists():
        urllib.request.urlretrieve(CHECKPOINT.url, pth)  # noqa: S310 (a fixed https URL)
    try:
        digest = manifest.check_download(pth, CHECKPOINT)
    except manifest.ModelError as e:
        pth.unlink()
        raise SystemExit(e.message) from e
    print(f"checkpoint sha256 {digest}")

    spec = importlib.util.find_spec("mmpose")
    if spec is None or spec.origin is None:
        raise SystemExit("mmpose is not installed in this environment")
    root = Path(spec.origin).parent
    print("patched:", patch_mmpose(root) or "nothing to patch")

    import torch
    from mmengine.config import Config
    from mmpose.apis import init_model

    cfg = Config.fromfile(str(root / ".mim" / "configs" / CONFIG))
    cfg.model.backbone.init_cfg = None
    cfg.model.neck.norm_cfg = dict(type="BN")  # SyncBN is for multi-GPU training
    model = init_model(cfg, str(pth), device="cpu")

    class SimCC(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, x):
            return self.m.head(self.m.extract_feat(x))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        SimCC(model).eval().cpu(),
        torch.zeros(*INPUT_SHAPE),
        str(args.out),
        input_names=["input"],
        output_names=OUTPUT_NAMES,
        opset_version=OPSET,
        dynamo=False,
    )
    import onnxruntime as ort

    session = ort.InferenceSession(str(args.out), providers=["CPUExecutionProvider"])
    print("contract ok:", manifest.check_onnx_io(session))
    size, digest = args.out.stat().st_size, manifest.sha256_of(args.out)
    print(f"exported {args.out.name}: {size} bytes, sha256 {digest}")
    print(f"(phase 1 reference export was {manifest.POSE_ONNX_BYTES} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
