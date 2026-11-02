# New swim datasets (underwater + overwater), searched 2026-11-02

Builds on reviews/real-swim-pose-datasets.md (2026-10-14). Only new finds here.

## Best new find
**SWIM-360 Static** (University of Malta)
- Repo: https://github.com/UM-SWIM-360/swim-360-static-cv-dataset
- Images: https://huggingface.co/datasets/UM-SWIM-360/swim360-static-cv-dataset (face-blurred; size not checked)
- 3,903 real frames, 3,757 swimmer labels, 44 videos, 15 swimmers, 4 strokes, 4K (3840x2160)
- Views: fixed lane camera, 32 underwater videos + 12 above-water videos
- Labels: COCO-17 keypoints with visibility flags (no hands/feet), train/valid/test split
- License: Apache-2.0 (repo sidebar)
- Access: clone repo, `python fetch_from_hf.py ...`, then `python compile_coco.py ...` (README file names don't quite match the repo; check)
- Use: first real test set for stock RTMW-x body points, and real fine-tune data. Split by video/swimmer, not by frame.
- A sibling "swim-360-dynamic-cv-dataset" is mentioned in the README (not checked).

## Real swim videos, no labels
**"Videos of Swimming for Every Type of Stroke"** (same Malta team, Zenodo, 2026, CC BY 4.0)
- Split into records: STARTS https://zenodo.org/records/19438588, TURN https://zenodo.org/records/19450891,
  SWIM2 part 001 https://zenodo.org/records/19882319, part 002 https://zenodo.org/records/19912136 (19.9 GB)
- Underwater lap footage, all strokes, many swimmers. Big multi-part 7-Zip archives. Views/counts not stated (only one record could be read).
- Likely the raw source for SWIM-360. Good for testing on long real clips.

## Small Roboflow sets (CC BY 4.0 or unknown, keypoints unverified)
- swimAI (Nunnari Labs) https://universe.roboflow.com/nunnari-labs-afqwc/swimai/dataset/35 : keypoints, 327 images in v35 (787 in project); related project "freestyle_backstroke_9_keypoints". License not shown.
- Deep Dive Pose Race https://universe.roboflow.com/deep-dive-qpwkt/deep-dive-pose-race : keypoints, CC BY 4.0, contents unverified (sister of Deep Dive Pose Technique).

## Not useful
- DUTH Swimmers Dataset: open-sea swimmer boxes for rescue, no pose.
- Roboflow keypoint-detection-competitive: detects walls/meter marks, not swimmers.
- Sensors 2026 "3D Human Pose Estimation ... Underwater Scenarios" (PMC13469234): page blocked, data availability unknown.

Roboflow, Hugging Face and Zenodo downloads are blocked or rate-limited from the cloud container, so downloads run on Joon's Mac or Colab.
