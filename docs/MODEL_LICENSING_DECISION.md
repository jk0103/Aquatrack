# Model licensing: what is known, what is not, and the decision to make

Prepared 2026-11-16 for the owner's decision. **Nothing here is legal advice, and nothing
has been decided, published, purchased or sent.** No licence file has been added to the
repository, its visibility is unchanged, and nobody has been contacted.

Three kinds of statement are kept apart throughout:

- **Official text**: what a licence or an official page says.
- **Licensor's policy**: how the licensor itself says its licence applies. This can go
  further than the licence text; it is their position, not a court's.
- **Unresolved**: a question the sources do not answer and that needs the rights holder's
  answer or professional legal review.

Sources were read on 2026-11-16 (pages fetched and read as text; GitHub issues through the
public API). Quotations are short; re-open the page before relying on exact wording.

## 1. The models

| | Detector | Pose model |
| --- | --- | --- |
| Model | YOLO11m, pretrained on COCO | RTMW-x, 384x288, 133 keypoints |
| File the worker loads | `yolo11m.pt` (40,684,120 bytes) | `rtmw_x_stock.onnx` (368,740,410 bytes), our own ONNX export |
| Published by | Ultralytics, release `ultralytics/assets` v8.3.0 | OpenMMLab MMPose, RTMW project |
| Source URL | github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt | download.openmmlab.com/mmpose/v1/projects/rtmw/rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth |
| Used through | the `ultralytics` Python package (unmodified, a dependency) | `rtmlib` + ONNX Runtime; MMPose itself is only used to export |
| Where it runs | server side only, in the inference worker | server side only, in the inference worker |
| Provenance in our results | file hash and library version are recorded with every pose run (Phase 8) | the same; the reference export's SHA-256 is `5ff227bf…7b29` |

Nothing is redistributed: no weights are in the repository, in the web app, or sent to users.

## 2. YOLO11 (Ultralytics)

### Official text

- The repository's `LICENSE` is the unmodified GNU AGPL-3.0. The README offers two options:
  AGPL-3.0 or the Ultralytics Enterprise License.
- AGPL-3.0, section 13: the duty to offer source to network users arises "if you modify the
  Program" and users interact with that modified version remotely. Section 2 affirms
  "unlimited permission to run the unmodified Program". Section 0: mere network interaction
  without transferring a copy "is not conveying". Sections 4 to 6 (notices, whole-work
  licensing, corresponding source) attach to conveying copies.
- The AGPL text does not mention model weights.
- Enterprise Software License (ultralytics.com/legal/enterprise-software-license, dated
  2024-07-05): a non-exclusive, non-transferable licence for any purpose including
  commercial; paid by an annual fee; one-year term that renews automatically unless notice
  is given 45 days before it ends; on non-renewal, use must stop. The licensee may be a legal
  entity or an individual. The price is not published (quoted on request).
- A Startups programme exists for VC-backed, for-profit companies. No academic or student
  Enterprise programme was found.

### Licensor's policy (Ultralytics' own statements)

- ultralytics.com/license: an Enterprise licence is listed as required for "Any commercial
  product or service", for "SaaS platforms, APIs, or cloud systems that use YOLO behind the
  scenes", for internal business tools, and for "R&D projects that are not fully
  open-sourced".
- The free AGPL column lists academic research and coursework, personal projects and
  learning, and "Evaluating Ultralytics YOLO in a fully open-source environment", framed by
  being comfortable open-sourcing the entire project.
- Compliance under AGPL is described as publicly releasing the complete source "for the
  entire derivative work, including the larger application", scripts, configuration and,
  where applicable, model weights.
- Trained and pretrained models are stated to be AGPL-3.0 by default; a maintainer has said
  that exporting to ONNX or avoiding the Ultralytics runtime "doesn't change that" (GitHub
  issue #22458). The exporter writes an AGPL licence string into exported files.
- In the same issue Ultralytics agreed that AGPL itself permits commercial and private use,
  the point being that closed use needs full AGPL compliance, and called the AGPL text the
  authoritative terms.

Where the policy goes beyond the licence text: it has no "if you modify" condition, it asks
for public release rather than an offer to remote users, and it names weights and
configuration files.

### Unresolved

1. Whether a server application that imports the unmodified package is a "modified version"
   or "work based on the Program" under AGPL sections 0 and 13.
2. Whether the AGPL covers the weights, or an ONNX export of them, as a matter of law.
3. Whether Ultralytics' "entire project" reaches a separate web frontend that talks to the
   backend over HTTP, and the non-inference parts of the backend.
4. Whether any trial or evaluation is permitted for a private repository. None was found.
5. The Enterprise price for a project of this size, and whether an individual or a student
   project qualifies for any discount.

## 3. RTMW-x (OpenMMLab)

### Official text

- MMPose code: Apache-2.0 (`LICENSE`, README). `LICENSES.md` lists exceptions; RTMPose and
  RTMW are not among them. There is no `NOTICE` file.
- rtmlib code: Apache-2.0. ONNX Runtime: MIT.
- **No official OpenMMLab page states a licence or terms of use for the pretrained
  checkpoints**, including this one. The RTMW project page only lists download links. The
  RTMW paper (arXiv 2407.08634) says code and models are publicly available and states no
  licence for them.
- Apache-2.0 covers "the Work" and derivative works of it, and on distribution requires a
  copy of the licence, retained notices and marked changes. Whether a checkpoint is part of
  "the Work" is not stated anywhere official.
- The checkpoint was trained on 14 datasets ("cocktail14"). Their own pages say:

| Dataset | Terms found on its own page |
| --- | --- |
| COCO-WholeBody | "ONLY for research and non-commercial use"; commercial use: contact the address in its README; annotations belong to SenseTime Research. The README's text says CC BY 4.0 while its link points to CC BY-NC 4.0 |
| MPII | annotations BSD; "Commercial use is not allowed" because of image copyright |
| 300W | research purposes only; "use in training commercial algorithms" is not allowed |
| InterHand2.6M | CC BY-NC 4.0 |
| Human-Art | authorisation for non-commercial purposes; "CC" licence, variant not named |
| LaPa | README: non-commercial purposes; repository licence file: Apache-2.0 (the two conflict) |
| COFW | CC BY 4.0 (CaltechDATA record) |
| AI Challenger, CrowdPose, Halpe, UBody, WFLW, sub-JHMDB, PoseTrack18 | no terms found, page gone, or host unreachable |

  Underlying COCO: annotations CC BY 4.0; images under their Flickr terms.

### Maintainer and third-party statements (not licence texts)

- An MMPose collaborator (also first author of COCO-WholeBody), 2022: check the training
  dataset's licence; some datasets "forbid commercial usage".
- An MMPose collaborator (RTMPose author), 2023: MMPose projects are licensed with
  permission for commercial use (said about the code). 2024, about other pretrained weights:
  "please feel free to use it"; follow-up questions about dataset licences are unanswered.
- rtmlib README: for weights trained on non-commercial datasets such as COCO-WholeBody, see
  its issue #65, and review the datasets' terms.
- rtmlib issue #65: a user relays an email said to be from the COCO-WholeBody authors, that
  models trained on it cannot be used commercially without a commercial licence. This is a
  third-party relay and cannot be verified.
- Several open MMPose issues asking for checkpoint licence terms have no maintainer reply.

### Unresolved

1. What terms, if any, OpenMMLab attaches to the RTMW-x checkpoint itself.
2. Whether the terms of a training dataset restrict the use of a model trained on it. This is
   a contested legal question; no licensor's page settles it, and it must not be assumed
   either way.
3. Whether converting the checkpoint to ONNX, or running it server side without distributing
   it, changes anything. No source addresses it.
4. The terms of seven of the fourteen datasets.
5. What a commercial licence from the COCO-WholeBody rights holder would cost or require.

What can be said: a research or non-commercial project is within the wording of every
dataset restriction found. A paid hosted service is exactly the case those restrictions
are about, and is **not cleared**.

## 4. The strategies

| | A. Open-source AquaTrack under AGPL-3.0 | B. Ultralytics Enterprise licence | C. Replace the detector |
| --- | --- | --- | --- |
| What it requires | Publish the service's source under AGPL-3.0 and offer it to users. By Ultralytics' policy: the whole project, publicly | Request a quote, sign, pay yearly; stop using on non-renewal | Choose a permissively licensed person detector, validate it, re-run the reference clips |
| Solves YOLO11 | Yes, by the licensor's own policy | Yes | Yes (YOLO11 is no longer used) |
| Solves RTMW-x | **No** | **No** | **No** |
| GitHub repository | Becomes public, with an AGPL `LICENSE`; history stays as it is | May stay private; no licence file needed for that reason | No change for this reason |
| Frontend and backend | Published too if "entire project" is followed; the safe reading is everything | No change | Backend: the detector class and model manifest; frontend: none |
| Cost | No fee. Anyone may reuse the code under AGPL | Annual fee, not published | Engineering time; no licence fee |
| Maintenance | Source must stay available for every deployed version | Renewal every year; lapse means removal | A new model to maintain; the Phase 1 comparison must be repeated for it |
| Student ownership and attribution | The student's authorship stays in the history and copyright notices; every contributor must agree to the licence; the student's research code becomes public | Licensee would be an individual or an entity: to be decided who | None |
| Extra technical work | Licence file, notices, a source link in the app, a check that nothing private is in the history | None | Significant: selection, validation, new thresholds; needs the owner's agreement (model research is closed) |
| Controlled development testing now | See section 5 | See section 5 | Not needed for testing |

Switching the Python library while keeping the YOLO weights does not resolve anything:
Ultralytics states that its weights stay AGPL in any runtime.

None of the three settles RTMW-x. For the pose model the options are separate:

- **P1. Stay non-commercial.** A free student or research project is within the wording of
  the dataset restrictions found. Still unconfirmed for the checkpoint itself.
- **P2. Ask.** Put the questions in section 7 to the MMPose maintainers and the
  COCO-WholeBody contact, and act on written answers.
- **P3. Legal review** before any paid service.
- **P4. A different pose model** whose training data allows commercial use: a larger change
  than replacing the detector, with the whole metric validation to redo. A contingency only,
  to be proposed separately if P1 to P3 fail.

### What this means in combination

| Goal | Detector | Pose model |
| --- | --- | --- |
| Free, open, non-commercial student project | A is sufficient by Ultralytics' policy | P1, ideally confirmed by P2 |
| Private repository, free service | B, or C | P1/P2 |
| Paid service | B (or A, if an open-source paid service is acceptable), or C | **Blocked** until P2/P3 give a clear answer, or P4 |

## 5. A private technical evaluation (the proposed GPU test)

The proposed test runs the unmodified `ultralytics` package and the RTMW-x export once, on
public video, in a private container, for no users and no money.

- **Under the licence texts**: AGPL-3.0 section 2 permits running the unmodified program,
  nothing is conveyed, and no user interacts with it over a network, so the conditions of
  section 13 are not met on their face. The dataset terms found allow research and
  non-commercial use.
- **Under Ultralytics' published policy**: evaluation is offered "in a fully open-source
  environment", and R&D that is not fully open-sourced is listed under Enterprise. A test in
  a private repository is therefore not something Ultralytics' page clearly permits.
- **So**: the evaluation looks low-risk and consistent with the licence texts, but it is not
  confirmed by the licensor. The owner decides whether to (a) run it on that basis, (b) ask
  Ultralytics first, or (c) choose strategy A or B first. This document does not decide it.

Conditions if it is run before the licensing direction is chosen: one-off, no users, no
payment, public test video only, image and weights deleted afterwards, weights never
redistributed, and the fact of the test recorded.

## 6. Attribution and notices

Whatever is chosen, a deployed AquaTrack should state: YOLO11 by Ultralytics (and under
which licence it is used); RTMW / RTMPose by OpenMMLab MMPose (Apache-2.0 code) with the
RTMW citation; rtmlib (Apache-2.0); ONNX Runtime (MIT); and the dataset citations the RTMW
authors ask for. Under strategy A, AGPL notices and a source link in the app. No wording is
prescribed by Ultralytics for AGPL users; none has been written into the app yet.

## 7. Questions to send (drafts; **not sent**)

Routes are the ones published on the official pages.

**To Ultralytics** (licensing request form on ultralytics.com/license):

1. AquaTrack is a student project: a web service that analyses swimming videos. It uses the
   unmodified `ultralytics` package and pretrained `yolo11m.pt` server side only, for person
   detection; no weights or code are distributed to users. Is a one-off private technical
   evaluation, with no users, covered by AGPL-3.0, or does it need an Enterprise licence?
2. If the project's source is published under AGPL-3.0, does that cover running it as a free
   hosted service? Must the separate web frontend and the non-inference backend also be
   AGPL?
3. What would an Enterprise licence cost for a single small project run by an individual,
   and is there any academic or student arrangement?
4. Is there required attribution wording for AGPL use?

**To the MMPose maintainers / RTMW authors** (GitHub issues on open-mmlab/mmpose; the
authors' addresses printed on the RTMW paper):

1. Under what terms is the checkpoint
   `rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth` released? Is it
   covered by the repository's Apache-2.0 licence?
2. May it be used, converted to ONNX, for server-side inference in (a) a free
   non-commercial service and (b) a paid service, without redistributing the weights?
3. Do the terms of the cocktail14 training datasets, in your understanding, restrict such
   use, and is there a checkpoint trained only on commercially usable data?

**To the COCO-WholeBody contact** (the address in the dataset's README):

1. Does the non-commercial restriction on the COCO-WholeBody annotations extend to using a
   third-party model (RTMW-x from MMPose) that was trained partly on them, for server-side
   inference, without access to or redistribution of the dataset?
2. If a commercial licence is needed for that, what are its terms?

## 8. Decisions for the owner

1. Is AquaTrack to stay a free, non-commercial project for now? (Decides most of this.)
2. Detector: A, B or C.
3. May the private GPU evaluation run before that choice (section 5)?
4. May the questions in section 7 be sent, and by whom (the owner, or the student as author)?
5. Is legal review wanted before any hosted, public use?

Until these are answered: no licence file, no publication, no public deployment, and
commercial use stays blocked.
