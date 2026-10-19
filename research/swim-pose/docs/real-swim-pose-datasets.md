# Real-human datasets for the swim pose model

Searched 2026-10-14. Everything comes from each dataset's own web page or paper, linked below. Anything I could not read is marked **(not verified)**.
I couldn't download anything to check it: Roboflow, Hugging Face and the MPII download server are all blocked from my side.

## Short answer

I found no public dataset of **real swimmers** that has both pose labels and the original videos.
The closest options are:

- **Real swimmers:** a small labeled set of 405 frames.
- **Real people in general:** large labeled sets.
- **Real swim videos:** clips with no labels, which we would label ourselves.

The plan at the end mixes all three with the SwimXYZ data we already have.

## 1. Real swimmers, labeled, public

| Dataset | What's in it | Labels | License | Notes |
|---|---|---|---|---|
| [Deep Dive Pose Technique](https://universe.roboflow.com/deep-dive-qpwkt/deep-dive-pose-technique) (Roboflow Universe) | 405 real swimmer frames. Version 6 is split 285 train / 81 valid / 39 test. File names point to GoPro clips filmed underwater from the side (`GoPro_Underwater_7ft_SideView`, `.MOV`). | Keypoints, class "Swimmer". The page doesn't list the keypoint names **(not verified)**. | CC BY 4.0 | **Best real-swimmer option found.** Images are stretched to 640×640, and the source videos are not included. Use the "Download Dataset" button. It likely needs a free Roboflow account **(not verified)**. Their own model scores mAP50 0.927. |
| [Swimming Dataset](https://universe.roboflow.com/swimming-dataset) (Roboflow) | 144 images | Keypoints | Not stated | Skip unless the license is clarified. |
| [Deep Dive Pose Race](https://universe.roboflow.com/deep-dive-qpwkt/deep-dive-pose-race) (Roboflow) | The page showed 0 images | Keypoints | CC BY 4.0 | Empty or unpublished. |
| [Swim](https://platform.ultralytics.com/vladislav-kutikov/datasets/swim) (Ultralytics Platform) | ? | ? | ? | The page wouldn't load **(not verified)**. |

## 2. Real people, labeled, public (not swimming-specific)

| Dataset | Frames / video | Labels | License | Fit for us |
|---|---|---|---|---|
| [COCO-Pose](https://docs.ultralytics.com/datasets/pose/coco/) | 56,599 train + 2,346 val photos, no video | Same 17 keypoints as our model | CC BY 4.0 (per the Ultralytics page) | **Fixes the "forgot standing people" problem.** Ultralytics downloads it automatically (`coco-pose.yaml`, ~20 GB). A subset of 5–10k photos is enough to mix in. |
| [MPII Human Pose](https://www.mpi-inf.mpg.de/departments/computer-vision-and-machine-learning/software-and-datasets/mpii-human-pose-dataset) | ~25k photos, 40k people, 410 activities including a "water activities" group. Each photo comes with the video frames before and after it. | 16 joints, a different set from COCO (no eyes or ears), so it needs conversion | Research only, no commercial use | The photos are 12.9 GB. The videos come in 25 batches of ~17 GB each. The page doesn't say how many photos show swimming. |
| [PoseTrack](https://arxiv.org/abs/1710.10000) | 550 videos taken from MPII's raw videos, ~23k labeled frames | 15 joints | Research benchmark | The paper describes everyday activities and doesn't mention swimming. |

## 3. Real swim videos, no labels (to label ourselves or test on)

- **[UCF101](https://www.crcv.ucf.edu/data-sets/ucf101/)**: 13,320 short YouTube clips, 6.5 GB, per [TensorFlow Datasets](https://www.tensorflow.org/datasets/catalog/ucf101).
  - From memory, its classes include BreastStroke, FrontCrawl and Diving, and the clips are low resolution, but the UCF page blocked me **(not verified)**.
- **Kinetics**: from memory, it has swimming backstroke, breaststroke, butterfly and front crawl classes. These are YouTube links, and many have been deleted **(not verified)**.
- **Your own clips** are the best match for the app, since they show real pools, real cameras and your swimmers.

## 4. Real swim pose data that is NOT public

These would need an email to the authors:

- [Cao & Yan 2023](https://link.springer.com/article/10.1007/s11042-023-16618-w): 2,500 underwater images, 3,615 swimmers, 14 keypoints, all 4 strokes. Data availability: "not applicable".
- [SwimmerNET](https://www.mdpi.com/1424-8220/23/4/2364) (Sensors 2023): underwater 2D pose, not released.
- [Dronaquatics](https://openaccess.thecvf.com/content/WACV2026/papers/Tran_Dronaquatics_Real-time_Swimming_Analytics_Using_Drone_Captured_Imagery_WACV_2026_paper.pdf) (WACV 2026): 100 drone videos, 2,632 frames, COCO-17, owned by a swimming association.
- [Augsburg deep sports pose](https://www.uni-augsburg.de/en/fakultaet/fai/informatik/prof/mmc/research/research_projects/deep_sports_pose): no public download. The contact is Katja Ludwig.
- [SwimTrack](https://multimediaeval.github.io/editions/2022/tasks/swimtrack/) (MediaEval 2022): competition participants only, and it covers tracking, not pose.
- [Diver pose dataset](https://arxiv.org/html/2510.17863v1) (2025): 3,305 real underwater stereo images with 20 keypoints. The paper doesn't mention a release.
- [KadyT/Swimmer](https://huggingface.co/KadyT/Swimmer/blob/main/README.md) (Hugging Face): a YOLO11-pose **model** with 7 keypoints, trained on 28k side-view images. The data isn't linked.
- [Sensors 2026 underwater 3D paper](https://www.mdpi.com/1424-8220/26/15/4738): uses SwimXYZ plus ~2,000 public underwater images, and doesn't say whether those are released.
- [This article](https://medium.com/@vanessa.camilleri/dive-into-smarter-swimming-why-ai-and-open-data-could-revolutionise-the-pool-020313660c1e) also says no fully open real-swim dataset exists.

**Couldn't read:**

- the [RTMPose swimmer talent paper](https://link.springer.com/chapter/10.1007/978-3-032-07336-5_17) (the site rate-limited me)
- the Tandfonline 2026 paper (the fetch failed)
- the Ultralytics "Swim" page

## 5. Suggested plan

Keep SwimXYZ as the base and add real data on top:

1. **COCO-Pose subset (5–10k photos).** This brings back standing and other non-swimming people. I can add it to the Colab notebook, since it needs no labeling.
2. **Deep Dive Pose Technique (405 real swimmers).** Download it from Roboflow in "YOLOv8 Pose" format and check its keypoints.
   - If they match the 17 COCO points, or can be mapped to them, train on its train split and keep its 39-image test split as **our first real test set**.
   - If not, use it only for testing the box and visible joints.
3. **Label 100–300 frames from real swim videos** (your clips first, UCF101 FrontCrawl if you need more) in CVAT.
   - Pre-label them with the current model so you only fix mistakes. The recovery-arm wrists and the ankles need the most fixing.
4. Then retrain, optionally with yolo11s-pose, and compare on the real test set, not just the synthetic swimmer.

## 6. Deep Dive Pose Technique, in detail (checked 2026-10-15)

Read from its Roboflow pages: [overview](https://universe.roboflow.com/deep-dive-qpwkt/deep-dive-pose-technique), [v6](https://universe.roboflow.com/deep-dive-qpwkt/deep-dive-pose-technique/dataset/6), [v1](https://universe.roboflow.com/deep-dive-qpwkt/deep-dive-pose-technique/dataset/1), [model 6](https://universe.roboflow.com/deep-dive-qpwkt/deep-dive-pose-technique/model/6) and [workspace](https://universe.roboflow.com/deep-dive-qpwkt).
The image, browse, health and download pages block automated reading, and Roboflow is blocked from both my container and your Mac's shell. So I couldn't open a single image or label file **(keypoints not verified)**.

**What it is**

- 405 frames, keypoint detection, class "Swimmer". A stray second class "0" is also listed, probably a leftover from import.
- License: CC BY 4.0, so credit the author if we use it.
- Made by a Roboflow workspace called "Deep Dive". The page doesn't name a person, team or website.
  - The workspace has 0 stars and 0 downloads, so nobody else has tested it publicly.
  - Its sister projects are "Deep Dive" (object detection, 405 images, probably the same frames with boxes only) and "Deep Dive Pose Race" (0 images).

**Version history**

| Version | Date | Images | Split | Processing |
|---|---|---|---|---|
| v1, v3, v4, v5 | 2025-05-17 to 05-19 | 149 | v1: 104 / 30 / 15 | Auto-orient, stretch to 640×640, no augmentation |
| v6 (latest) | 2025-05-28 | 405 | 285 / 81 / 39 (70/20/10) | Auto-orient, stretch to 640×640, no augmentation |

**Where the frames come from**

The file names show the frames were cut from a small number of real videos, not separate photos:

- iPhone clips: `IMG_1684`, `IMG_3479`, `IMG_3483`, `IMG_3489`, `IMG_0216`, `IMG_8220`, `IMG_8517`, `IMG_8520`, `IMG_9281`, `IMG_9420`, `IMG_9503`, `IMG_9507`, `IMG_9513` (`.MOV`)
- One GoPro clip: `4_6_25_GoPro_Underwater_7ft_SideView_Landscape` (underwater, side view, 7 ft deep, filmed 6 Apr 2025)

That's 14 different clips in the ~36 file names I could see, and the full set probably has a few more. The pages don't say which stroke, or whether the iPhone clips are above or below water **(not verified)**.

**Their model**

- Roboflow 3.0 Keypoint Detection (Accurate), started from a COCO-pose checkpoint, trained 2025-05-28.
- It scores mAP50 0.927, precision 0.908 and recall 0.904.

**Three things to watch**

1. **Leaky test split.** Roboflow splits frames at random, so frames from the same clip land in both train and test. Neighbouring frames look almost identical, which makes the 0.927 score look better than it would be on a new video. For our own test set, re-split by clip: hold out 2–3 whole clips, matching on the `IMG_xxxx` prefix.
2. **Stretched images.** Every frame was squashed or stretched to 640×640, so swimmers look wider or thinner than they are.
   - Labels are stored as fractions of the image size, so resizing an image back to its original shape (likely 16:9 for "Landscape" clips) keeps the labels correct.
   - We need the original aspect ratio per clip. The shape of the joints, or asking the author, would tell us.
3. **Keypoints unknown.** Our model uses the 17 COCO points.
   - If Deep Dive uses the same 17 in the same order, it plugs straight in.
   - If it uses a different set, I write a small mapping and mark the missing points as "not labeled" (visibility 0), which Ultralytics handles.
   - Either way, check `kpt_shape` and `flip_idx` in its `data.yaml`. A wrong `flip_idx` silently swaps left and right during training.

**How to get it**

1. Sign in to Roboflow with a free account.
2. Open [v6](https://universe.roboflow.com/deep-dive-qpwkt/deep-dive-pose-technique/dataset/6) and click **Download Dataset**.
3. Pick the **YOLOv8** format (Ultralytics pose, the same as ours) and **Download zip to computer**.
4. Share the zip. Next steps are to read the keypoint list and draw every label on its frame to check quality, re-split by clip, convert it to our 17-point format if needed, and add it to the Colab notebook.
