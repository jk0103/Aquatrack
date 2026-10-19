# AquaTrack: review before building our own swim pose model

Reviewed 2026-10-12, read-only. Nothing on your Mac was created, changed, moved or deleted.
Everything below was checked in the files under `~/Desktop` unless marked **(not verified)**.

## 1. Project structure

There are two separate places, and they don't talk to each other yet.

**`~/Desktop/Aquatrack`** — the web app (git repo, on branch `claude/login-signup`, 3 commits on top of the initial one).

| Path | What it is |
|---|---|
| `src/aquatrack/analysis/pose/base.py` | `Joint` (13 joints), `PoseSequence`, `PoseEstimator` interface |
| `src/aquatrack/analysis/pose/yolo_backend.py` | `YoloPoseEstimator`: runs Ultralytics YOLO on each video frame, keeps the largest person |
| `src/aquatrack/analysis/metrics/` | `stroke_rate.py`, `symmetry.py`, `signal.py` |
| `src/aquatrack/analysis/video.py` | frame reading |
| `src/aquatrack/api/` | FastAPI: `/health`, `/videos` upload (stores file, returns size/fps), login/signup |
| `frontend/` | Next.js login/signup pages |
| `tests/` | pytest, including `test_pose.py` (uses fake arrays, no real model) |
| `data/` | `aquatrack.db` (SQLite) and a README; no sample videos |

**`~/Desktop/pose-practice`** — class practice, not in git, its own `.venv` (Python 3.11.4, ultralytics 8.4.173, torch 2.14.1).

| Path | What it is |
|---|---|
| `pose_photo.py`, `pose_video.py` | run a YOLO pose model on a photo / video and draw the result |
| `images/`, `videos/swim_underwater.mp4`, `output/` | test inputs and drawn results |
| `yolo11n-pose.pt`, `yolo11s-pose.pt` | pretrained Ultralytics weights |
| `labeling/` | CVAT practice: 3 hand-labeled photos + 1 no-person photo, `train_swim.py`, `check_labels.py`, `cvat_skeleton_coco17.json` |
| `swimxyz/` | SwimXYZ subset, `build_dataset.py`, `train.py`, `remote_zip.py`, two trained runs, logs, README |

## 2. Existing YOLO Pose implementation and training scripts

- **App inference:** `yolo_backend.py`, default model `yolo26n-pose.pt`, confidence 0.25, maps COCO-17 keypoints onto 13 `Joint`s (drops eyes and ears). The model name is a parameter, so a custom `.pt` can be passed in. Nothing in `src/` references the SwimXYZ model yet.
- **Practice inference:** `pose_photo.py` / `pose_video.py`, `--model` flag picks any weights.
- **Training script 1:** `labeling/train_swim.py`, 200 epochs on the 3 CVAT photos (train and val are the same folder). Overfit, kept as a teaching example.
- **Training script 2:** `swimxyz/train.py`, starts from `yolo11n-pose.pt`, 30 epochs, imgsz 640, batch 16, `freeze=10`, patience 10.
- **Dataset builder:** `swimxyz/build_dataset.py` streams only the needed files out of the SwimXYZ zips on Zenodo (HTTP range requests in `remote_zip.py`), converts labels and writes a YOLO dataset.

Note a version mismatch: the app uses **yolo26n-pose**, while all training so far started from **yolo11n-pose**. Both are COCO-17 so the output format matches, but they are different architectures.

## 3. SwimXYZ files available

Only a small subset is on disk (`swimxyz/`, 472 MB total). The full dataset is **not** downloaded.

- `cache/`: 24 source videos (`video_01.webm` … `video_24.webm`, 349 MB). Freestyle only, views `Side_underwater` and `Side_water_level`, 4 swimmers × 3 videos × 2 views.
- `dataset/` (36 MB): first version, full frames only. 205 train / 63 val images.
- `dataset_zoom/` (56 MB): second version, full frames + zoomed swimmer crops. 406 train (199 zoom) / 138 val (69 zoom).
- `labels_list.txt`, `videos_list.txt`, `videos2_list.txt`: file listings of the remote zips. The label zip lists 5 camera views (Aerial, Front, Side_above_water, Side_underwater, Side_water_level).
- The original SwimXYZ 2D label text files were read straight from the zip and **not** saved locally; only the converted YOLO labels exist.
- The README says the full dataset is over 150 GB **(not verified here; it's from the earlier write-up)**.

## 4. Dataset structure

- **Videos:** `.webm`, synthetic (rendered) swimmers.
- **Images:** frames sampled from the videos, 20 per video, saved as JPG resized to 960×540. Zoom crops keep 16:9 but vary in size. Frames with fewer than 8 joints inside the image are dropped.
- **Split:** by swimmer. `Swimmer_Skin_0,75_Muscle_8` is validation only, the other 3 are training. Same pool scenes and camera views appear in both splits.
- **Original annotations:** per video `COCO/2D_cam.txt`, semicolon-separated, comma decimals, 18 joints in **OpenPose order** (Nose, Neck, RShoulder…). Y is measured from the bottom, so the builder flips it and adds a 6-pixel shift found by overlaying labels on video.
- **Converted annotations:** one `.txt` per image, one line, YOLO pose format: `class cx cy w h` then 17 × `x y v`, all normalized. Every one of the 544 label files has exactly 56 values. The box is computed from the joints with 8% padding (SwimXYZ boxes were not used).
- **Visibility:** only `2` (inside the frame) or `0` (outside the frame). There is no "occluded but inside" `1` value, so joints hidden behind the body or under bubbles are still marked visible.

## 5. Compatibility with Ultralytics YOLO Pose

- **Converted SwimXYZ labels: compatible.** `data.yaml` has `kpt_shape: [17, 3]`, a correct COCO-17 `flip_idx`, and one class `person`. Ultralytics trained on it without errors (both logs completed 30 epochs).
- **Raw SwimXYZ labels: not compatible as-is.** 18 OpenPose joints, bottom-origin Y, CSV-like text. They need the conversion in `build_dataset.py` (OpenPose → COCO-17 table `TO_COCO17`).
- **CVAT exports: almost compatible.** `labeling/export/data.yaml` lacks `flip_idx`; `train_swim.py` adds it when it builds `labeling/dataset/`.
- **Portability catch:** both SwimXYZ `data.yaml` files hold an absolute path (`/Users/<you>/Desktop/pose-practice/...`), so they only work on this Mac unless regenerated.

## 6. CPU or GPU

Confirmed from the run files, not guessed:

| Run | Device | Evidence |
|---|---|---|
| `swimxyz/runs/swim` | **MPS (Apple GPU)** | `args.yaml` `device: mps`; `train.log` "torch-2.14.1 MPS (Apple M5)" |
| `swimxyz/runs/swim_zoom` | **MPS (Apple GPU)** | same, in `args.yaml` and `train_zoom.log` |
| `labeling/runs/swim` | **CPU** | `args.yaml` `device: cpu` |

`train.py` picks `mps` automatically when available, else `cpu`. Training time from `results.csv`: about 296 s (swim) and 433 s (swim_zoom) for 30 epochs. No NVIDIA/CUDA training anywhere. Inference in `pose_photo.py`/`pose_video.py` was described as CPU in project notes **(not re-verified in this review)**.

## 7. Results so far (from `results.csv` and the SwimXYZ README)

Final epoch on the held-out synthetic swimmer:

| Run | Box mAP50 | Pose mAP50 | Pose mAP50-95 |
|---|---|---|---|
| swim | 0.995 | 0.817 | 0.223 |
| swim_zoom | 0.984 | 0.786 | 0.227 |

The README's "합성 검증 관절 점수 0.82 / 0.79" is the **pose mAP50**. The stricter pose mAP50-95 is only about 0.22, so keypoints land near the right place but not precisely. On real photos (README): swim_zoom finds the underwater photo at 0.70 and the swimming photo at 0.83, but the standing-person photo drops from 0.92 to 0.03 (forgetting). These real-photo checks are 3 images, not a test set.

## 8. What can be reused

- `build_dataset.py` + `remote_zip.py`: the whole SwimXYZ download-and-convert pipeline, including the joint mapping, Y flip, visibility rule and zoom crops. Just widen `VIEWS`, strokes, videos and frames per video.
- `swimxyz/train.py`: working training recipe with MPS/CPU auto-detection, freezing and early stopping.
- `swim_zoom/weights/best.pt`: a usable starting checkpoint and baseline to beat.
- The swimmer-held-out validation split idea.
- CVAT workflow, `cvat_skeleton_coco17.json` and `check_labels.py` for labeling real footage.
- `pose_photo.py` / `pose_video.py` for visual checks of any model.
- In the app: the `PoseEstimator` interface and `YoloPoseEstimator(model=...)`, so a custom model plugs in with no new code path; the metrics modules consume its output.

## 9. Missing requirements

1. **No real labeled swim test set.** Only 3 hand-labeled photos and 1 underwater clip. We can't measure real-world accuracy, which is what matters.
2. **Small, narrow training data.** 544 images from 24 videos, freestyle only, 2 of 5 views, 4 swimmers, all synthetic.
3. **No general-person data mixed in**, which caused the forgetting.
4. **No occlusion labels** (visibility is only 0 or 2).
5. **Training lives outside the repo.** Scripts, dataset config and weights are not versioned; `data.yaml` paths are absolute.
6. **App not connected to the trained model**, and app (yolo26n) vs training (yolo11n) base models differ.
7. **No upload → analysis → results flow** in the API yet (`/videos` only stores the file).
8. **No experiment tracking** beyond run folders (no record of which dataset version produced which weights).
9. **Licensing:** SwimXYZ is CC BY 4.0 per the README (attribution needed); Ultralytics is AGPL **(both from notes, not re-checked)**.

## 10. Recommended next steps

1. **Build a real test set first.** Label 50–100 frames from real underwater and overhead clips in CVAT, using the existing skeleton. Never train on it.
2. **Decide the base model.** Either train from `yolo26n-pose` to match the app, or switch the app to yolo11n. Recommendation: train from yolo26n-pose so the app needs no change.
3. **Scale the SwimXYZ subset** with `build_dataset.py`: more videos per swimmer, more strokes, add `Side_above_water` and `Aerial` if overhead video matters. Watch disk space.
4. **Mix in COCO person images** (for example 20–30% of the training set) to stop forgetting standing people.
5. **Move training into the repo** (for example `training/`), with relative dataset paths, and keep datasets and weights out of git.
6. **Train on MPS** as before, compare against `swim_zoom/best.pt` on both the synthetic val split and the real test set.
7. **Wire the best model into `YoloPoseEstimator`** through a setting, then connect upload → pose → metrics → results page.
