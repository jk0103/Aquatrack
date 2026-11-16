#!/usr/bin/env bash
# Phase 9B: the first real GPU inference test, as commands. PREPARED, NEVER RUN.
#
# NOT TO BE RUN without the owner's separate approval of the provider, the permitted model
# use, the billing exposure, the resources created and the execution itself
# (docs/PHASE_9B_EXECUTION.md). Run it from Google Cloud Shell, not from the owner's Mac:
# the Mac has neither gcloud nor docker, and nothing is downloaded to it.
#
#   export PROJECT_ID=...            # a NEW, dedicated test project (created by the owner)
#   export ACCEPT_MODEL_TERMS=yes    # the owner's acceptance; without it nothing builds
#   bash worker/phase9b.sh <step>
#
# Steps, one at a time, in this order: check setup build create run status fetch
#                                      stop cleanup verify
# Every paid step is bounded: one task, no retries, 15 minutes, one L4, one region.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID to the dedicated test project}"
REGION="us-central1"                      # the only region this script will use
REPO="aquatrack-test"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/worker:9b"
JOB="aquatrack-acceptance"
BUCKET="gs://${PROJECT_ID}-acceptance-out"
VIDEO_URL="https://upload.wikimedia.org/wikipedia/commons/9/9b/Front_Crawl_Underwater.webm"
VIDEO_SHA256="ce32d556ba1399b9dd5000f9a079475ca33377a9280cf30619a566ff8e9523c3"
MAX_EXECUTIONS=5                          # in total, failed starts included
TASK_TIMEOUT="15m"

g() { gcloud --project "${PROJECT_ID}" "$@"; }

executions_so_far() { g run jobs executions list --job "${JOB}" --region "${REGION}" --format="value(name)" 2>/dev/null | wc -l | tr -d " "; }

case "${1:-}" in
  check)   # read-only: what project, what billing, what already exists
    g config list 2>/dev/null || true
    gcloud billing projects describe "${PROJECT_ID}"
    g run jobs list --region "${REGION}" || true
    ;;
  setup)   # enables APIs, creates the image repository and the output bucket
    g services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com storage.googleapis.com
    g artifacts repositories create "${REPO}" --repository-format=docker --location="${REGION}"
    g storage buckets create "${BUCKET}" --location="${REGION}" --uniform-bucket-level-access
    ;;
  build)   # one Cloud Build, at most 45 minutes; uploads only the .gcloudignore allowlist
    [ "${ACCEPT_MODEL_TERMS:-no}" = "yes" ] || { echo "ACCEPT_MODEL_TERMS is not yes"; exit 2; }
    g builds submit --config worker/cloudbuild.yaml \
      --substitutions="_IMAGE=${IMAGE},_ACCEPT=yes" .
    ;;
  create)  # the job: 1 L4, 4 vCPU, 16 GiB, 1 task, no retries, 15 minutes
    g run jobs create "${JOB}" --region "${REGION}" --image "${IMAGE}" \
      --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
      --cpu 4 --memory 16Gi \
      --tasks 1 --parallelism 1 --max-retries 0 --task-timeout "${TASK_TIMEOUT}" \
      --add-volume "name=out,type=cloud-storage,bucket=${BUCKET#gs://}" \
      --add-volume-mount "volume=out,mount-path=/out" \
      --set-env-vars "AQUATRACK_ENV=test,AQUATRACK_POSE_DEVICE=cuda,AQUATRACK_MODELS_STRICT=1" \
      --command python \
      --args "scripts/gpu_acceptance.py,--video-url,${VIDEO_URL},--video-sha256,${VIDEO_SHA256},--out-dir,/out"
    ;;
  run)     # one execution; refuses once the agreed number has been used
    n="$(executions_so_far)"
    [ "${n}" -lt "${MAX_EXECUTIONS}" ] || { echo "already ${n} executions: the agreed maximum is ${MAX_EXECUTIONS}"; exit 2; }
    g run jobs execute "${JOB}" --region "${REGION}" --wait
    ;;
  status)
    g run jobs executions list --job "${JOB}" --region "${REGION}"
    ;;
  fetch)   # the report and the new RawPose (a few hundred kB) to ./phase9b-out
    mkdir -p phase9b-out
    g storage cp "${BUCKET}/acceptance.json" "${BUCKET}/${VIDEO_SHA256}.rawpose.npz" phase9b-out/
    g logging read "resource.type=cloud_run_job AND resource.labels.job_name=${JOB} AND textPayload:ACCEPTANCE_REPORT" --limit 5 --format="value(textPayload)" > phase9b-out/log-report.txt || true
    ls -la phase9b-out
    ;;
  stop)    # EMERGENCY STOP: end anything running, then remove the job
    for e in $(g run jobs executions list --job "${JOB}" --region "${REGION}" --format="value(name)" 2>/dev/null); do
      g run jobs executions cancel "${e}" --region "${REGION}" --quiet || true
    done
    g run jobs delete "${JOB}" --region "${REGION}" --quiet || true
    ;;
  cleanup) # everything this script created, then billing off, then the project
    g run jobs delete "${JOB}" --region "${REGION}" --quiet || true
    g artifacts repositories delete "${REPO}" --location "${REGION}" --quiet || true
    g storage rm --recursive "${BUCKET}" || true
    g storage rm --recursive "gs://${PROJECT_ID}_cloudbuild" || true
    echo "Now, by hand, in this order:"
    echo "  bash worker/phase9b.sh verify"
    echo "  gcloud billing projects unlink ${PROJECT_ID}"
    echo "  gcloud projects delete ${PROJECT_ID}"
    ;;
  verify)  # what still exists
    g run jobs list --region "${REGION}" || true
    g run services list || true
    g artifacts repositories list || true
    g storage buckets list --format="value(name)" || true
    g compute instances list 2>/dev/null || true
    gcloud billing projects describe "${PROJECT_ID}" || true
    ;;
  *)
    echo "usage: PROJECT_ID=... bash worker/phase9b.sh check|setup|build|create|run|status|fetch|stop|cleanup|verify"; exit 2 ;;
esac
