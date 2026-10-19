# Swim pose model research (Google Colab)

The record of how AquaTrack's swimmer pose model was chosen and trained. The app needs to find a swimmer's
joints in underwater and overhead video, and stock pose models built for people on land do badly in the pool.
Training and model comparisons ran in Google Colab, with files kept in Google Drive.

```
research/swim-pose/
├── README.md                                    this page: timeline, results, decisions
├── notebooks/
│   ├── aquatrack_swimxyz_finetune.ipynb         first Colab training (small SwimXYZ subset)
│   ├── aquatrack_swimxyz_full_freestyle.ipynb   training on all SwimXYZ freestyle videos
│   └── aquatrack_vitpose_vs_yolo.ipynb          side-by-side model comparisons (Parts 1 to 4)
└── docs/
    ├── swim-pose-model-review.md                review of the model work as of 2026-10-12
    └── real-swim-pose-datasets.md               search for real (not computer-generated) swim data
```

## Timeline (2026)

| Date | Step | Outcome |
|---|---|---|
| Sep 28 | App starts with the stock `yolo26n-pose` model | Chosen over MediaPipe for the first version |
| Oct 5 | Pretrained `yolo11n-pose` on an underwater photo | Missed the swimmer. A bigger input size, a lower threshold and `yolo11s-pose` didn't really help |
| Oct 5 | Fine-tuned on 3 photos hand-labeled in CVAT | Overfit badly, kept only as a class example |
| Oct 5 to 12 | Fine-tuned on a SwimXYZ subset on a Mac (24 freestyle videos, 544 images, Apple M5 GPU, about 7 minutes) | Found the underwater swimmer (0.70) but stopped finding standing people |
| Oct 12 | Review of the work so far | [docs/swim-pose-model-review.md](docs/swim-pose-model-review.md) |
| Oct 12 to 14 | Colab training on all 2,880 SwimXYZ freestyle videos (about 79 GB) | 40 epochs on a free T4, about 6.5 minutes per epoch. The free GPU limit stopped it at epoch 38, and it resumed later |
| Oct 14 | Trained model on real photos (notebook step B4) | Underwater photo found at 0.76 (stock model: 0.09). The out-of-water arm's wrist lands near the elbow, the ankles collapse together, and standing people come out poorly |
| Oct 14 to 15 | Search for real swim datasets | No public dataset of real swimmers has both labels and videos. [docs/real-swim-pose-datasets.md](docs/real-swim-pose-datasets.md) |
| Oct 19 | Off-the-shelf ViTPose-B inside our YOLO's swimmer box, against our YOLO (Part 1) | ViTPose placed the joints clearly better on both photos and on the underwater video |
| Oct 19 | More comparisons added: original `yolo11n` against ours (Part 2), ViTPose against MediaPipe (Part 3), hands and feet (Part 4) | Results pending |

## Results

| Model | Trained on | Pose mAP50 | Pose mAP50-95 | On real swim photos and video |
|---|---|---|---|---|
| `yolo11n-pose` + SwimXYZ subset (Mac, `swim_zoom`) | 406 train / 138 val images | 0.786 | 0.227 | Finds the underwater swimmer; forgets standing people |
| `yolo11n-pose` + all SwimXYZ freestyle (Colab, `swim_full`) | 22,106 train / 1,839 val images | 0.940 | 0.689 | Finds the swimmer; misplaces the wrist on the out-of-water arm and the ankles |
| ViTPose-B, off the shelf (COCO people only) | not retrained | not measured | not measured | Best joints of all on the photos and the video tested |

The mAP scores come from a held-out SwimXYZ swimmer. SwimXYZ is computer-generated, so those scores say little
about real pools, and judging on real photos and video mattered more. A labeled set of real swim frames is still
missing.

A MediaPipe Pose (heavy) run on the underwater clip found the swimmer in 92% of frames, but its legs folded onto
the hips in most frames, so its extra hand and foot points weren't trustworthy there.

## Decisions

- **Joints come from ViTPose, and the swimmer's box comes from our YOLO** (2026-10-19). ViTPose has COCO's
  same 17 joints, so the rest of the app stays the same. Switching the app over is on hold until more clips are
  tested.
- **Hand and foot points are wanted too.** The Hugging Face ViTPose only outputs 17 body points. Part 4 tests
  whole-body models (133 points: body, 3 per foot, 21 per hand, face): ViTPose-B whole-body and RTMW-x, through
  [rtmlib](https://github.com/Tau-J/rtmlib).
- **Licenses:** Ultralytics YOLO is AGPL-3.0, which is fine for personal and school use, but a paid product
  would need to be open source or buy a commercial license. ViTPose and rtmlib are Apache 2.0. The SwimXYZ
  license isn't stated, so its data isn't shared here.

## Running the notebooks

Open a notebook in Colab with **File > Open notebook > GitHub**, then paste this repository's URL. Each notebook
explains its own steps at the top.

- **`aquatrack_swimxyz_finetune.ipynb`**: the first Colab version. It uses 6 videos per swimmer, and everything
  is saved to `MyDrive/aquatrack_swim/`.
- **`aquatrack_swimxyz_full_freestyle.ipynb`**: the main training.
  - Part A runs on a CPU. It downloads each video from Zenodo, keeps 8 frames plus a zoomed crop, and builds 20
    resumable shards in `MyDrive/aquatrack_swim_full/shards/`.
  - Part B runs on a T4 GPU. It trains with automatic resume (B2), compares scores with the Mac model (B3), and
    tests on your own photo or video (B4).
- **`aquatrack_vitpose_vs_yolo.ipynb`**: the comparisons. Run cells 0 and 1, then the cells of any part. Results
  are saved to `MyDrive/aquatrack_swim_full/compare/`.
  - Part 1: ViTPose-B against our YOLO.
  - Part 2: the original `yolo11n` against ours.
  - Part 3: ViTPose-B against MediaPipe.
  - Part 4: whole-body models for hands and feet.

## Not in this repository

- **Model weights.** `best.pt` stays in Google Drive at `MyDrive/aquatrack_swim_full/runs/swim_full/weights/`.
  In a local checkout it goes in `models/swim_pose.pt`.
- **Training data.** SwimXYZ (Zenodo records 8399376, 8402009 and 8402031) is too big and has no stated license.
- **Swim photos and videos** used for testing, and the Colab outputs saved in Drive.
- **The early Mac scripts.** `build_dataset.py` and `train.py` from the SwimXYZ subset run live outside this
  repository. The Colab notebooks contain the same dataset recipe.

## Next steps

1. Run Parts 2, 3 and 4 of the comparison notebook on more real clips.
2. Build a real test set: Roboflow's Deep Dive Pose Technique (405 real frames, CC BY 4.0, re-split by clip),
   plus 100 to 300 frames from our own clips labeled in CVAT.
3. Pick the joint model (ViTPose-B, or a whole-body model if hands and feet hold up underwater) and plug it into
   the app behind the YOLO swimmer box.
4. Fine-tune on real and SwimXYZ frames together, scored on the real test set.
