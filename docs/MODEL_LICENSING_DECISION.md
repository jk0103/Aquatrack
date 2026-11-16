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
public API), in two passes; the second (Phase 9A) re-read Ultralytics' pages and closed
some gaps. Quotations are short; re-open the page before relying on exact wording.

**Short version.** Keeping AquaTrack free does not by itself settle anything: Ultralytics'
test is open source or not, not paid or not. Keeping the repository private does not by
itself forbid every experiment either: the AGPL text permits running the program privately.
Those two readings disagree about a private test, and only Ultralytics (or a lawyer) can
close that gap. For RTMW-x, nobody has published terms for the checkpoint at all.

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

- **Closed evaluation is sold separately.** Ultralytics' legal page lists paid "R&D License
  Terms" (single-project, dated 2026-03-03, and multi-project): internal research,
  evaluation and proof of concept for a fee, with no commercial or production rights. The
  licence page's own questionnaire answers "we're testing YOLO first" on the closed-source
  path with "You need a commercial license".
- Its compliance guide (docs.ultralytics.com/help/contributing) says what open-sourcing
  means to it: the whole derivative work public under AGPL-3.0, a LICENSE file and a notice
  in each source file, including training and inference scripts, configuration and
  Dockerfiles, and "Backend and frontend code if it's part of a web application", with a
  README line crediting Ultralytics YOLO.
- Staff statements (not licence text): on-premises or internal closed use needs Enterprise;
  separating processes with sockets "does not by itself exempt" the other process;
  interpretations vary and users should take their own advice.
- No academic, educational or student licence or discount is published. The only discount
  programme is for VC-backed for-profit startups.
- The words "student", "trial" and "non-commercial" do not appear in the licence page's FAQ.

Where the policy goes beyond the licence text: it has no "if you modify" condition, it asks
for public release rather than an offer to remote users, it names weights and
configuration files, and it treats private and internal use as needing a licence.

### What the licence text and the FSF say (official, but not Ultralytics)

- AGPL-3.0 section 0: to "propagate" excludes "executing it on a computer or modifying a
  private copy"; network interaction without a copy "is not conveying".
- Section 2: "unlimited permission to run the unmodified Program"; covered works you do not
  convey may be made and run without conditions.
- Section 13: applies "if you modify the Program" and users interact with it remotely.
- The FSF's GPL FAQ (its interpretation of its own licence): private modification and use
  need not be released; whether two programs form one work depends on how intimately they
  communicate, and "pipes, sockets and command-line arguments" are normally used between
  separate programs; a program's output is in general not covered. It says nothing about
  model weights.

These are the terms Ultralytics itself calls authoritative. They are narrower than its
policy pages, and no official page reconciles the two.

### Unresolved

1. Whether a server application that imports the unmodified package is a "modified version"
   or "work based on the Program" under AGPL sections 0 and 13.
2. Whether the AGPL covers the weights, or an ONNX export of them, as a matter of law.
3. Whether Ultralytics' "entire project" reaches a separate web frontend that talks to the
   backend over HTTP, and the non-inference parts of the backend.
4. Whether a one-off private evaluation by an individual, with no users, needs the paid
   R&D licence in Ultralytics' view. Its pages point that way; no page addresses exactly
   this case, and the licence text points the other way.
5. The Enterprise and R&D licence prices (not published), and whether an individual or a
   student project qualifies for anything.
6. Whether a free hosted service is fully covered by publishing the whole project under
   AGPL-3.0. Its pages present that as the alternative to Enterprise; no sentence says so
   in terms.

## 3. RTMW-x (OpenMMLab)

### Official text

- MMPose code: Apache-2.0 (`LICENSE`, README). `LICENSES.md` lists exceptions; RTMPose and
  RTMW are not among them. There is no `NOTICE` file.
- rtmlib code: Apache-2.0. ONNX Runtime: MIT.
- **No official OpenMMLab page states a licence or terms of use for the pretrained
  checkpoints**, including this one. The RTMW project page only lists download links; the
  model card (`rtmw_cocktail14.md`) has no usage wording; its metadata file has no licence
  field; the documentation's FAQ and model zoo pages do not contain the words "license" or
  "commercial"; the download host serves no terms page. The RTMW paper (arXiv 2407.08634)
  says code and models are publicly available and states no licence for them. The project
  README describes the models as designed "for practical applications".
- openmmlab.com could not be read (expired certificate on 2026-11-16), so terms there, if
  any, are unseen.
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
- Eight open MMPose issues asking for checkpoint licence terms (among them #3278, about an
  RTMW cocktail14 checkpoint) have no maintainer reply as of 2026-11-16.
- The rtmlib owner, 2026-11-07, about another checkpoint: he has "not checked their
  commercial licenses one by one" and suggests users check the datasets.
- Creative Commons' own FAQ on AI: its licences apply only where copyright permission is
  needed, and whether a use breaches a non-commercial condition depends on the facts. It
  does not say whether trained weights are an adaptation of the training works. Neither the
  FSF nor the OSI states a position on training-data terms carrying over to weights.

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

## 5. Decision table by kind of use

"Expressly permitted" means a rights holder's own page says so. "Disputed" means the licence
text and the licensor's policy point different ways. "Unresolved" means nobody has said.

### A. Free, non-commercial academic research (private repository, no public service)

| | YOLO11m | RTMW-x |
| --- | --- | --- |
| Expressly permitted | Academic research and coursework, "comfortable open-sourcing your entire project" (Ultralytics' free column). Running the unmodified program (AGPL section 2) | Research and non-commercial use, by every dataset restriction found |
| Disputed | Doing it **without** publishing the project: the licence text permits private use; Ultralytics lists non-open R&D under paid licences | nothing found |
| Unresolved | Whether Ultralytics would require its R&D licence for a one-off private test | Any terms for the checkpoint itself; seven datasets' terms |
| What would settle it | A written answer from Ultralytics, or publishing under AGPL-3.0, or the R&D licence | A written answer from the MMPose maintainers |

### B. Free, publicly accessible swimming application

| | YOLO11m | RTMW-x |
| --- | --- | --- |
| Expressly permitted | Open-source applications with the full source public under AGPL-3.0, web applications included (backend and frontend), per Ultralytics' compliance guide | nothing: no page addresses a public service |
| Not permitted without a licence, per the licensor | A free public service whose source is closed: "SaaS platforms, APIs, or cloud systems" need Enterprise. Being free of charge is not the test | — |
| Disputed | Whether section 13 is even triggered by an unmodified dependency behind a separate web frontend | Whether "non-commercial" dataset terms reach a free public service using a model trained on them |
| Unresolved | A literal statement that open-sourcing is sufficient for a hosted free service | Checkpoint terms; whether a free public service counts as non-commercial for each dataset owner |
| What would settle it | Strategy A (publish under AGPL-3.0) plus Ultralytics' written confirmation; or Enterprise | Written answers from MMPose and the COCO-WholeBody contact |

### C. Closed-source commercial application

| | YOLO11m | RTMW-x |
| --- | --- | --- |
| Expressly permitted | With an Enterprise licence (annual fee, price on request) | nothing |
| Not permitted without a licence, per the licensor | Any closed commercial product | COCO-WholeBody, MPII, 300W, InterHand2.6M, Human-Art and LaPa's README restrict commercial use of the data |
| Unresolved | Price and terms for a small project or an individual | Whether those data terms bind the trained weights; what a commercial licence from the COCO-WholeBody rights holder costs; six other datasets |
| What would settle it | A quote and a signed Enterprise licence, or replacing the detector | Written permission or licences from the rights holders, legal advice, or a different pose model |

### D. Paid swimming analysis SaaS

| | YOLO11m | RTMW-x |
| --- | --- | --- |
| Expressly permitted | Enterprise licence; or (by the AGPL's own terms) an open-source paid service with the whole source public | nothing |
| Not permitted without a licence, per the licensor | Closed SaaS using YOLO "behind the scenes" | the same data restrictions as C; this is the case they are written for |
| Unresolved | the same as C | the same as C. **This is the hardest blocker in the whole project** |
| What would settle it | the same as C | the same as C |

**No row above is legal clearance.** A is the only use for which nothing found speaks
against it, provided either the project is open or Ultralytics agrees; D is not cleared for
either model.

## 6. A private technical evaluation (the proposed GPU test)

The test runs the unmodified `ultralytics` package and the RTMW-x export once, on public
video, in a private container, for no users and no money.

| Reading | What it says about this test |
| --- | --- |
| AGPL-3.0 text and the FSF's FAQ | Permitted: running the unmodified program, nothing conveyed, no remote users |
| Ultralytics' published policy | Not covered for free while the project is closed: evaluation is free "in a fully open-source environment"; closed R&D and evaluation have their own paid licence |
| RTMW-x and its datasets | Research and non-commercial use is within every restriction found; the checkpoint has no stated terms |

So the test is **permitted on the licence text and not confirmed, arguably excluded, on the
licensor's own policy**. There is no documented permission from Ultralytics. The ways to run
it with the licensor's position respected, in order of effort:

1. **Ask first** (draft below) and run it after a written yes.
2. **Publish the project under AGPL-3.0 first** (strategy A): then the test is an evaluation
   in an open-source environment, which the free column lists.
3. **Buy the single-project R&D licence** (price not published).
4. **Run it on the licence text alone**, accepting that Ultralytics' pages do not agree.
   This is a risk the owner would be taking knowingly, not a cleared path.

This document does not choose. Conditions in any case: one-off, no users, no payment, public
test video only, image and weights deleted afterwards, weights never redistributed, the test
recorded.

## 7. Attribution and notices

- **Ultralytics, if AGPL**: a LICENSE file with the AGPL-3.0 text, a licence notice in each
  source file, a README stating the licence with build and run instructions and the credit
  line Ultralytics gives: "This project utilizes code from Ultralytics YOLO
  (https://github.com/ultralytics/ultralytics), licensed under AGPL-3.0." Citation is
  requested (its `CITATION.cff`; the YOLO11 docs give a BibTeX entry), not stated as a
  licence condition.
- **MMPose / rtmlib (Apache-2.0)**: keep copyright and licence notices and a copy of the
  licence when distributing their code; mark changed files. MMPose has no NOTICE file.
  Citations requested: RTMPose, MMPose, RTMW (`jiang2024rtmw`).
- **ONNX Runtime (MIT)**: keep its copyright and permission notice when distributing it.
- **Datasets**: the citations the RTMW authors and dataset owners ask for.
- **Test video**: "Front Crawl Underwater", author as named on Wikimedia Commons, CC BY-SA
  4.0, wherever it or anything derived from it is shown.

None of this has been added to the app or the repository; it follows the licensing choice.

## 8. Inquiry drafts (**not sent; nobody has been contacted; no permission has been given**)

Fill in the bracketed parts. Send from the person who will hold the licence or run the
project. The drafts state facts about AquaTrack as they are today.

### 8.1 Ultralytics

**Route:** the licensing form on https://www.ultralytics.com/license (the page says they
reply within 24 hours). The form asks for: first and last name, **business email**, company
size, **company website**, industry (the list includes Education), and a free-text use case
(up to 5,000 characters). There is no field for an individual or a student project, so say
so in the text. The page's fallback address is license@ultralytics.com; staff name the
Contact form (topic "Licensing") as the alternative.

**Use-case text / email:**

> Subject: Licensing question for a student project using YOLO11m (AGPL-3.0 / Enterprise / R&D)
>
> Hello,
>
> I am writing about AquaTrack, a swimming-technique analysis web application developed as
> a student project [by NAME, with TEACHER/INSTITUTION]. It is not a company and has no
> revenue. The repository is currently private.
>
> How we use your software: the unmodified `ultralytics` Python package (version 8.4.210)
> and the pretrained `yolo11m.pt` weights from your v8.3.0 release, for person detection
> only. It runs server side in a separate inference worker process. We have not modified
> your code, we do not train or fine-tune, and we do not distribute your code or weights to
> users. We do not export the model; it runs through your package.
>
> We would like to follow your licensing terms and would be grateful for written answers to
> the following:
>
> 1. Private evaluation. May we run a one-off, private, non-commercial technical test of the
>    unmodified package and weights on a cloud GPU (one public test video, no users, no
>    service offered) under AGPL-3.0, or does this require your R&D licence?
> 2. Privately hosted proof of concept. May a student-developed application use the
>    pretrained model in a privately hosted proof of concept with no public access, and
>    under which licence?
> 3. Open source. If we publish the project under AGPL-3.0, which parts must be published:
>    the inference worker only, the whole backend, the separate web frontend? Is publishing
>    the complete project sufficient to operate it as a free public web service?
> 4. Free public service. What applies to a free, public web service (no payment, no
>    advertising) if the source is published under AGPL-3.0, and if it is not?
> 5. Commercial SaaS. What licence would a paid subscription service need, and is there an
>    indicative price or minimum fee for a single small project run by an individual or a
>    very small team?
> 6. ONNX. If we exported `yolo11m.pt` to ONNX and ran it with ONNX Runtime, without your
>    package at run time, would any of the answers above change?
> 7. Academic terms. Is there an academic, educational, student or evaluation licence or
>    discount for the Enterprise or R&D licences?
> 8. Notices. Which copyright, licence and attribution notices must we retain or display
>    under AGPL-3.0, and under an Enterprise licence?
>
> We have not deployed the application and will not use the model beyond what you confirm.
> Thank you for your help.
>
> [NAME, ROLE, CONTACT]

### 8.2 OpenMMLab / MMPose maintainers and the RTMW authors

**Routes:** no licensing or business contact is published. What is published: GitHub
issues on https://github.com/open-mmlab/mmpose (an existing open issue, #3278, asks the same
question about RTMW cocktail14 weights and is unanswered; adding to it may be more useful
than a new issue); the authors' addresses printed on the RTMW paper (arXiv 2407.08634:
Tao Jiang, Xinchen Xie, Yining Li, Shanghai AI Laboratory); the package contact
openmmlab@gmail.com in MMPose's `setup.py`. A GitHub issue is public: write nothing private
in it.

> Subject: Usage terms of the RTMW-x cocktail14 checkpoint (rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth)
>
> Hello,
>
> Thank you for MMPose and RTMW. I am writing about AquaTrack, a swimming-technique analysis
> application developed as a student project. We use exactly one of your released models:
>
>   rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth
>   (RTMW-x, 384x288, 133 keypoints, from projects/rtmpose)
>
> We convert it to ONNX (backbone and head, opset 17, outputs simcc_x / simcc_y) and run it
> with ONNX Runtime through rtmlib, server side only. We do not retrain or fine-tune it, and
> we do not redistribute the checkpoint or the ONNX file.
>
> The repository states Apache-2.0 for the code, but we could not find terms for the
> pretrained checkpoint itself, and the model card lists fourteen training datasets, some of
> which restrict commercial use. Could you tell us:
>
> 1. Under what licence or terms is this checkpoint released? Is it covered by the
>    repository's Apache-2.0 licence?
> 2. Is private, non-commercial, research-only evaluation of it on a GPU permitted?
> 3. May a student-developed application use it in a privately hosted proof of concept?
> 4. If the project is published as open source, what must we do regarding the checkpoint
>    (we would not include the weights; users would download them from your host)?
> 5. May it be used in a free, public web service?
> 6. What would be required for a paid commercial service? Is there a written commercial
>    licensing process, or a checkpoint trained only on data that permits commercial use?
> 7. Does converting it to ONNX change any of these conditions?
> 8. Which copyright, licence or citation notices should we retain or display?
>
> We understand you may not be able to speak for the dataset owners; your own position as
> the publisher of the checkpoint would already help us a great deal.
>
> Thank you.
>
> [NAME, ROLE, CONTACT]

### 8.3 COCO-WholeBody rights holders

**Route:** the dataset's README (https://github.com/jin-s13/COCO-WholeBody, "Terms of Use",
item 2) names a contact for commercial use, with a second person in copy. Use the addresses
exactly as printed there. Note for the owner: the README's text names CC BY 4.0 while its
link points to CC BY-NC 4.0; question 1 asks about that.

> Subject: Use of a third-party model trained partly on COCO-WholeBody (RTMW-x from MMPose)
>
> Dear Mr. Malon, dear Dr. Jin,
>
> I am writing about AquaTrack, a swimming-technique analysis application developed as a
> student project. We do not use, hold or redistribute the COCO-WholeBody dataset or its
> annotations. We use a pretrained model published by OpenMMLab MMPose,
> `rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth`, whose model card
> lists COCO-WholeBody as one of fourteen training datasets. We run it for inference only,
> server side, converted to ONNX.
>
> Your Terms of Use state that the dataset is only for research and non-commercial use and
> ask that you be contacted for commercial usage. We would like to respect them and ask:
>
> 1. Which licence applies to the annotations: CC BY 4.0, as the README text says, or
>    CC BY-NC 4.0, as its link indicates?
> 2. Do your terms apply to the use of a third-party model that was trained partly on
>    COCO-WholeBody, when the user has no access to the dataset?
> 3. Is private, non-commercial, research-only evaluation of such a model permitted?
> 4. Is use in a student-developed, privately hosted proof of concept permitted?
> 5. Is use in a free, public web service permitted?
> 6. For a paid commercial service, is a licence from you required, and if so is there a
>    written licensing process and an indicative price?
> 7. Does converting the model to ONNX change anything?
> 8. Which notices or citations should we retain or display?
>
> We have not deployed the application and will not use the model commercially without
> your answer.
>
> Thank you for your time.
>
> [NAME, ROLE, CONTACT]

## 9. Decisions for the owner

1. Which of A to D is AquaTrack meant to be, now and later? (Section 5.)
2. Detector strategy: open-source under AGPL-3.0, an Ultralytics licence (R&D or
   Enterprise), or a replacement.
3. The private GPU test: which of the four ways in section 6.
4. May the drafts in section 8 be sent, and by whom (the owner, or the student as author)?
5. Is legal review wanted before any hosted, public use?

Until these are answered: no licence file, no publication, no public deployment, no
inquiry sent, and commercial use stays blocked.
