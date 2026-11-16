# The AquaTrack inference worker: YOLO11m + RTMW-x on a GPU. PREPARED, NEVER BUILT.
#
# Building downloads model weights whose licences are not settled
# (docs/MODEL_LICENSING_DECISION.md) and about 3 GB of Python packages. It must happen in
# a cloud build, never on the owner's Mac, and only after the owner approves:
#
#   gcloud builds submit --config worker/cloudbuild.yaml      (docs/PHASE_9B_EXECUTION.md)
#
# No weights are in the repository or the build context (.dockerignore is an allowlist).
# The detector comes from Ultralytics' own release; the pose model is exported in a
# throw-away stage from the checkpoint on OpenMMLab's own download host. Nothing comes from
# a personal Drive or Colab. The manifest written here pins the exact files; the worker
# refuses to start if they change.
#
# CUDA: there is no CUDA base image. The locked PyTorch (2.14.0) brings the CUDA 13 and
# cuDNN 9 libraries as pip packages, and onnxruntime-gpu is pinned to a release that
# ONNX Runtime documents as built for CUDA 13.0 and cuDNN 9 (1.27 to 1.30). Both therefore
# use the same libraries, which is what ONNX Runtime requires. The NVIDIA driver itself is
# mounted by Cloud Run (580.x, "13.0" per Google's GPU page). An earlier draft used a CUDA 12
# base image with an unpinned onnxruntime-gpu, which would have installed a CUDA 13 build
# against CUDA 12 libraries; that mismatch is what this layout removes.
# NOT VERIFIED until a build and a GPU run: that these versions load together on the L4.

# ---- stage 1: export the pose model (a tool chain the worker itself does not need)
FROM python:3.11-slim AS export
ARG ACCEPT_MODEL_TERMS=no
RUN test "$ACCEPT_MODEL_TERMS" = "yes" || (echo "Model terms not accepted: see docs/MODEL_LICENSING_DECISION.md" && false)
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
# CPU-only PyTorch is enough to export. mmengine / mmcv-lite / mmpose / mmdet are the
# versions of the Phase 1 export. numpy is held below 2 because the prebuilt xtcocotools
# wheel for Python 3.11 dates from 2023. mmpose and mmdet are installed without their
# declared dependencies (one of them, chumpy, has no wheel and is not needed to export),
# so what they import is listed here by hand.
RUN pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir "numpy<2" "opencv-python-headless<4.12" onnx "onnxruntime<1.24" \
       mmengine==0.10.7 xtcocotools==1.14.3 json_tricks munkres scipy pillow matplotlib \
       pycocotools shapely terminaltables six tqdm pydantic \
    && pip install --no-cache-dir --no-deps mmcv-lite==2.1.0 mmpose==1.3.2 mmdet==3.3.0
COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
ENV PYTHONPATH=/src/src TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
RUN python scripts/export_rtmw_onnx.py --self-check \
    && python scripts/export_rtmw_onnx.py --out /models/rtmw_x_stock.onnx --accept-model-terms \
    && python scripts/fetch_models.py --models-dir /models --accept-model-terms --add rtmw_x_stock.onnx

# ---- stage 2: the worker
FROM python:3.11-slim AS worker
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 zlib1g ca-certificates \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY scripts ./scripts
# The locked application dependencies plus the pose extra (ultralytics 8.4.210, the version
# that produced the reference pose; PyTorch with its CUDA 13 libraries), then the GPU build
# of ONNX Runtime in place of the CPU one (the two cannot be installed together).
RUN uv sync --locked --no-dev --extra pose \
    && uv pip uninstall onnxruntime \
    && uv pip install "onnxruntime-gpu>=1.30,<1.31"
COPY --from=export /models /models
# Run as an unprivileged user; the image holds no credentials of any kind.
RUN useradd --create-home --uid 10001 worker && chown -R worker /app
USER worker
ENV PATH="/app/.venv/bin:$PATH" \
    AQUATRACK_MODELS_DIR=/models \
    AQUATRACK_MODELS_STRICT=1 \
    AQUATRACK_POSE_SOURCE=local \
    AQUATRACK_POSE_DEVICE=cuda \
    AQUATRACK_WORKER=external
# Fails the build if the files, manifest or pose model contract are wrong. The GPU itself
# can only be checked where there is one: the same check runs again when the worker starts.
RUN AQUATRACK_POSE_DEVICE=cpu AQUATRACK_ENV=test python -m aquatrack.worker --check
# Work through whatever is queued, then exit, so nothing idles on a billed GPU.
ENTRYPOINT ["python", "-m", "aquatrack.worker"]
CMD ["--drain"]
