"""Export the public RTMW-x checkpoint to the ONNX file the worker loads.

    python scripts/export_rtmw_onnx.py --out /models/rtmw_x_stock.onnx --accept-model-terms

For a worker image build stage only. DO NOT RUN on the owner's Mac (it downloads a
checkpoint of several hundred MB) and not before the licensing decision in
docs/MODEL_LICENSING_DECISION.md.

It needs the export tool chain, which the worker itself does not: torch, mmengine 0.10.7,
mmcv-lite 2.1.0, mmpose 1.3.2, mmdet 3.3.0, onnx (the versions the Phase 1 export used; see
worker/Dockerfile). The steps are the ones used for the Phase 1 reference export:

1. download the checkpoint from OpenMMLab's own download host and check that its SHA-256
   starts with the eight characters in its file name (OpenMMLab's convention);
2. build the model from mmpose's own cocktail14 384x288 config, with SyncBN replaced by BN;
3. export backbone + head with outputs named simcc_x and simcc_y, opset 17;
4. check the result against the contract the estimator relies on.

Exports are not bit-for-bit reproducible: the hash of the file made here will differ from
the Phase 1 export (5ff227bf...). That is expected; what must hold is the input and output
contract here and the comparison with the reference pose in the acceptance test.
"""

import argparse
import sys
import urllib.request
from pathlib import Path

from aquatrack.analysis.pose import manifest

CHECKPOINT = manifest.SOURCES["rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth"]
CONFIG = "wholebody_2d_keypoint/rtmpose/cocktail14/rtmw-x_8xb320-270e_cocktail14-384x288.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("/tmp/rtmw-export"))
    parser.add_argument("--accept-model-terms", action="store_true")
    args = parser.parse_args()
    if not args.accept_model_terms:
        print("Refusing to run: read docs/MODEL_LICENSING_DECISION.md first.", file=sys.stderr)
        return 2

    args.work.mkdir(parents=True, exist_ok=True)
    pth = args.work / CHECKPOINT.name
    if not pth.exists():
        urllib.request.urlretrieve(CHECKPOINT.url, pth)  # noqa: S310 (a fixed https URL)
    digest = manifest.sha256_of(pth)
    if not digest.startswith(CHECKPOINT.sha256_prefix):
        raise SystemExit(
            f"checkpoint hash {digest[:8]} does not match its name ({CHECKPOINT.sha256_prefix})"
        )
    print(f"checkpoint sha256 {digest}")

    import mmpose
    import torch
    from mmengine.config import Config
    from mmpose.apis import init_model

    cfg = Config.fromfile(str(Path(mmpose.__file__).parent / ".mim" / "configs" / CONFIG))
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
        torch.zeros(1, 3, 384, 288),
        str(args.out),
        input_names=["input"],
        output_names=["simcc_x", "simcc_y"],
        opset_version=17,
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
