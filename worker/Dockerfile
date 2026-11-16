# The AquaTrack inference worker: YOLO11m + RTMW-x on a GPU, taking jobs from the Firestore
# queue. PREPARED, NEVER BUILT. Building it downloads model weights whose licences are not
# settled (docs/MODEL_LICENSING_DECISION.md) and must happen in the cloud build environment,
# not on the owner's Mac. Build only after the owner approves:
#
#   docker build -f worker/Dockerfile --build-arg ACCEPT_MODEL_TERMS=yes -t aquatrack-worker .
#
# No weights are in the repository or the build context. The detector comes from
# Ultralytics' own release, the pose model is exported in a throw-away stage from the
# checkpoint on OpenMMLab's own download host. Nothing comes from a personal Drive or Colab.
# The manifest written here pins the exact files; the worker refuses to start if they change.

# ---- stage 1: export the pose model (tool chain that the worker itself does not need)
FROM python:3.11-slim AS export
ARG ACCEPT_MODEL_TERMS=no
RUN test "$ACCEPT_MODEL_TERMS" = "yes" || (echo "Model terms not accepted: see docs/MODEL_LICENSING_DECISION.md" && false)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
# CPU-only torch is enough to export. Versions are the ones the Phase 1 export used.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir "setuptools<81" cython numpy "opencv-python-headless>=4.10" \
       onnx onnxruntime mmengine==0.10.7 json_tricks munkres scipy pillow xtcocotools \
    && pip install --no-cache-dir --no-deps mmcv-lite==2.1.0 mmpose==1.3.2 mmdet==3.3.0
COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
RUN pip install --no-cache-dir --no-deps -e .
ENV TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
RUN python scripts/export_rtmw_onnx.py --out /models/rtmw_x_stock.onnx --accept-model-terms
RUN python scripts/fetch_models.py --models-dir /models --accept-model-terms --add rtmw_x_stock.onnx

# ---- stage 2: the worker
# CUDA 12 runtime with cuDNN 9: what onnxruntime-gpu 1.20+ and the PyTorch CUDA wheels need.
# Cloud Run mounts the NVIDIA driver itself; the CUDA libraries have to be in the image.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS worker
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends python3.11 python3.11-venv python3-pip \
    libgl1 libglib2.0-0 ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY scripts ./scripts
# The locked application dependencies plus the pose extra, then the GPU build of ONNX
# Runtime in place of the CPU one (the two packages cannot be installed together).
RUN uv sync --locked --no-dev --extra pose --python 3.11 \
    && uv pip uninstall onnxruntime \
    && uv pip install "onnxruntime-gpu>=1.20,<2"
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
# can only be checked where there is one: the same command runs again when the worker starts.
RUN AQUATRACK_POSE_DEVICE=cpu AQUATRACK_ENV=test python -m aquatrack.worker --check
# Work through whatever is queued, then exit, so nothing idles on a billed GPU.
ENTRYPOINT ["python", "-m", "aquatrack.worker"]
CMD ["--drain"]
