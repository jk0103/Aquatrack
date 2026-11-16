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

## 0. Project direction (decided by the owner, 2026-11-16)

**AquaTrack is, permanently, a completely free, noncommercial student research and
educational project.** There is no plan for a paid service, a commercial SaaS or a
subscription, now or in the future. Commercial licensing is therefore not an objective of
this document any more; the commercial facts found are kept in sections 2 and 3 only
because they explain what the rights holders restrict.

What this decision does and does not do:

- It removes the hardest question (commercial use of a model trained on noncommercial
  data) from the project's path.
- **It does not by itself resolve the licensing.** Ultralytics' test is open source or not,
  not paid or not: a free service with closed source still needs its licence, by its own
  pages. And the RTMW-x checkpoint still has no stated terms at all.
- Keeping the repository private does not by itself forbid every experiment either: the
  AGPL text permits running the program privately. Text and licensor's policy disagree
  about a private test, and only Ultralytics (or a lawyer) can close that gap.
- The models stay: YOLO11m and RTMW-x are kept unless their terms force an alternative.
- Three uses are checked separately, because their requirements differ (section 5):
  private research, open-source publication, and a free publicly accessible application.
- Nothing is published, licensed, purchased or sent on the strength of this decision.

## 0.1 Permission status

Two kinds of record are kept apart here and must never be merged:

- **Owner's report**: what the owner has told the project.
- **Reviewed written evidence**: the rights holder's own words, read by whoever maintains
  this record, with who wrote them, when, and through which channel.

### Owner's report (2026-11-16)

The owner reports having received confirmation from Ultralytics and from "the relevant
RTMW-x parties" that their models may be used for this noncommercial student project.

**Reviewed written evidence: none yet.** The confirmations themselves have not been seen by
the maintainer of this record. Until they have been read, the licensing blockers are
recorded as **"permission reported by the owner; scope not verified"**, not as resolved.
This is not doubt about the report; it is that a one-line summary cannot show which uses a
confirmation covers, and the uses differ.

### What each confirmation has to show

To be filled in from the written text, per rights holder. "Not stated" is a valid entry and
means that use is still open for that party.

| Scope item | Ultralytics (YOLO11m) | MMPose / RTMW authors (checkpoint) | COCO-WholeBody rights holders |
| --- | --- | --- | --- |
| Who confirmed, in what role, when, by what channel | to verify | to verify | to verify |
| Which model exactly (package version, `yolo11m.pt`; the cocktail14 384x288 checkpoint) | to verify | to verify | to verify |
| Private development with the repository still closed | to verify | to verify | to verify |
| Cloud GPU inference (a hosted worker, not only a local machine) | to verify | to verify | to verify |
| Model weights: downloading and holding them in a container image | to verify | to verify | not applicable |
| ONNX conversion | to verify (we do not convert YOLO11m today) | to verify | to verify |
| Free public deployment (anyone can sign up; no charge) | to verify, **and whether the source must be published under AGPL-3.0 for it** | to verify | to verify |
| Open-source publication of our code | to verify (which parts) | to verify | to verify |
| Attribution or notices required | to verify | to verify | to verify |
| Redistribution of weights or converted models | to verify | to verify | to verify |
| Conditions, limits, expiry, "this is not a licence" wording | to verify | to verify | to verify |

Open points that a general "you may use it for a noncommercial student project" would not
settle by itself:

1. **Ultralytics and source publication.** Its published position is that the alternative
   to a paid licence is open-sourcing the whole project. A confirmation may mean "yes, under
   AGPL-3.0" (which implies publishing before a public deployment) or "yes, even closed".
   These lead to different next steps.
2. **Who "the relevant RTMW-x parties" are.** The checkpoint's publisher (OpenMMLab / the
   RTMW authors) and the COCO-WholeBody rights holders are different parties, and the
   checkpoint was trained on fourteen datasets. A confirmation from one does not speak for
   the others. The other thirteen dataset owners were not asked; six of the fourteen carry
   research-only or noncommercial wording, which a noncommercial project is within.
3. **Private test against public deployment.** A reply to a question about a one-off private
   evaluation does not necessarily cover an application open to the public.
4. **Form.** A support reply, a forum post and a signed licence differ in weight. Record what
   it is; do not upgrade it.

### What the report changes now, and what it does not

- For the **private GPU evaluation (Phase 9B)**: the model-use decision is the owner's to
  make, and the owner reports permission. That item of the decision gate is recorded as
  "owner reports permission; written scope not yet reviewed". The other gate items
  (provider, billing exposure, resources, execution) are unchanged and still need the
  owner's separate explicit authorisation.
- For **open-source publication and a free public application**: nothing changes until the
  written scope is reviewed. No licence file, no change of repository visibility, no
  deployment.
- For the **models**: unchanged. YOLO11m and RTMW-x, as prepared.

### Where the written confirmations go

In `docs/private/licensing/` (ignored by git; never committed): the messages as received,
with sender, date and channel. Personal contact details stay there and are not copied into
tracked files; this document records only the party, the date, the channel and the scope.

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
5. Whether a free, public application counts as noncommercial use in each dataset owner's
   sense.

What can be said: a research or noncommercial project, which AquaTrack permanently is, is
within the wording of every dataset restriction found. That is not the same as the
checkpoint's publisher or the dataset owners having confirmed it. (Paid use is exactly what
those restrictions are about; it is out of scope by the owner's decision.)

## 4. The options that fit a free student project

### Detector (YOLO11m)

| | A. Open-source AquaTrack under AGPL-3.0 | C. Replace the detector | B. Ultralytics paid licence |
| --- | --- | --- | --- |
| Fit with the project's direction | **The natural fit**: Ultralytics' free column is written for open, academic and personal projects | A contingency only | **Not an objective.** A commercial licence for a noncommercial project; no purchase without the owner's separate approval |
| What it requires | Publish the whole project publicly under AGPL-3.0 (by Ultralytics' guide: backend, frontend, scripts, configuration, Dockerfiles), with a LICENSE file, notices and the credit line | Choose a permissively licensed person detector, validate it, re-run the reference clips | A quote, a signature, a yearly fee (price not published); R&D variant for closed evaluation only |
| Solves YOLO11 | Yes, by the licensor's own policy | Yes (YOLO11 is no longer used) | Yes |
| Solves RTMW-x | **No** | **No** | **No** |
| GitHub repository | Becomes public, with an AGPL `LICENSE`; history stays as it is | No change for this reason | May stay private |
| Cost | No fee. Anyone may reuse the code under AGPL | Engineering time | A fee |
| Before it can be done | **Contributor rights confirmed** (below); nothing private in the history; the owner's explicit approval | The owner's agreement (model research is closed) and new validation | The owner's approval and a decision on who the licensee is |
| Extra technical work | Licence file, per-file notices, README section, a source link in the app | Significant | None |

Switching the Python library while keeping the YOLO weights does not resolve anything:
Ultralytics states that its weights stay AGPL in any runtime.

**Contributor rights, before any publication under AGPL-3.0.** A licence can only be applied
by those who hold the rights. To confirm first: (1) the student, as author of the original
project and holder of the commits made in their name, agrees to publish under AGPL-3.0;
(2) the teacher's contributions and the AI-assisted work committed under the student's
identity are covered by that agreement; (3) the three early commits authored as "Claude" are
accounted for; (4) third-party material is cleared or removed, in particular the hero photo
whose source is not recorded; (5) the full history holds nothing private (it is published
with the code); (6) if the work was done within a school, whether the school has any claim
or policy. None of this has been checked with the people concerned.

### Pose model (RTMW-x)

- **P1. Rely on the project being noncommercial.** A free student and research project is
  within the wording of every dataset restriction found. Unconfirmed for the checkpoint
  itself, which has no stated terms.
- **P2. Ask.** Put the questions in section 8 to the MMPose maintainers and the
  COCO-WholeBody contact, and act on written answers. Answers may be slow or never come.
- **P3. A different pose model**, only if the terms turn out to forbid even free use: a
  large change with the whole metric validation to redo; to be proposed separately.

### In combination

| Use | Detector | Pose model |
| --- | --- | --- |
| Private research and evaluation | disputed while the project is closed (section 6) | P1; nothing found against it |
| Open-source publication | A, after contributor rights are confirmed | code references only; no weights are published |
| Free public application | A is the fitting route; closed source would need a paid licence | P1, ideally confirmed by P2 |

## 5. Requirements by kind of use

Checked separately, because being free and noncommercial does not make them the same.
"Expressly permitted" means a rights holder's own page says so. "Disputed" means the licence
text and the licensor's policy point different ways. "Unresolved" means nobody has said.

### 5.1 Private research and evaluation (private repository, no users, no service)

| | YOLO11m | RTMW-x |
| --- | --- | --- |
| Expressly permitted | Running the unmodified program (AGPL-3.0 section 2; private use is not conveying). Academic research and coursework, in Ultralytics' free column, framed by open-sourcing the project | Research and noncommercial use, by every dataset restriction found |
| Disputed | Doing it **while the project is closed**: the licence text permits it; Ultralytics' pages list closed R&D and evaluation under paid licences | nothing found |
| Unresolved | Whether Ultralytics would ask a student for its R&D licence for a one-off private test | Any terms for the checkpoint itself; seven datasets' terms |
| What would settle it | A written answer from Ultralytics, or publishing under AGPL-3.0 first | A written answer from the MMPose maintainers |

### 5.2 Open-source publication (the code made public; no service offered)

| | YOLO11m | RTMW-x |
| --- | --- | --- |
| Expressly permitted | Publishing a project that uses the package under AGPL-3.0: this is what Ultralytics asks for | Publishing code that uses MMPose-derived tooling: Apache-2.0, keep notices |
| Required | The whole project under AGPL-3.0, publicly: LICENSE file, notice in each source file, README with licence, build and run instructions and the Ultralytics credit line; scripts, configuration and Dockerfiles included; backend and frontend | Apache-2.0 notices for any MMPose or rtmlib code that is copied (we copy none today; we depend on rtmlib) |
| Weights | Not in the repository; users fetch `yolo11m.pt` from Ultralytics. If weights were ever published they would be AGPL by Ultralytics' statement | Not in the repository; users fetch the checkpoint from OpenMMLab and export it. **Do not publish our ONNX export**: redistribution rights for the checkpoint are unknown |
| Unresolved | Whether every part of the repository (web frontend, non-inference backend) must be AGPL; the safe reading is all of it | Whether naming and scripting the download of a checkpoint without terms needs anything |
| Preconditions on our side | Contributor rights (section 4); nothing private in the history; the owner's explicit approval. **Not done, not started** | the same |

Publication also affects other things than the models: the public test clips are CC BY-SA
and are not in the repository; the evidence and training sources are cited, not copied.

### 5.3 Free, publicly accessible application (anyone can sign up and upload; no charge)

| | YOLO11m | RTMW-x |
| --- | --- | --- |
| Expressly permitted | Open-source applications with the full source public under AGPL-3.0, web applications included, per Ultralytics' compliance guide | nothing: no page addresses a public service |
| Not permitted without a licence, per the licensor | A free public service whose source is closed: "SaaS platforms, APIs, or cloud systems" need its licence. **Free of charge is not the test** | — |
| Disputed | Whether AGPL section 13 is even triggered by an unmodified dependency behind a separate web frontend. Complying anyway (offering the source) removes the question | Whether a free public service counts as "noncommercial" in each dataset owner's sense when a model trained on the data is used. For CC BY-NC material Creative Commons says it depends on whether the use is primarily for commercial advantage; the other datasets use their own wording |
| Unresolved | A literal statement from Ultralytics that open-sourcing is sufficient for a hosted free service | Checkpoint terms; the same seven datasets |
| What would settle it | Strategy A plus Ultralytics' written confirmation | Written answers from MMPose and the COCO-WholeBody contact |
| Other duties a public service brings | Under AGPL: a visible way for users to get the source of the running version | Privacy and data-protection duties for users' videos, which no licence covers (`docs/DATA_LIFECYCLE.md`) |

**None of these is legal clearance.** In short: private research is permitted by the licence
texts and not confirmed by Ultralytics; open-source publication is the route Ultralytics
itself offers and waits on contributor rights and the owner's approval; a free public
application is, for the detector, the same route plus source access for users, and for the
pose model rests on its being noncommercial, which nobody has confirmed for the checkpoint.

### Out of scope by decision

Closed-source commercial use and paid services are not pursued. For the record only: they
would need an Ultralytics Enterprise licence and, for RTMW-x, clearance that does not exist
today (sections 2 and 3). If the project's direction ever changed, this would have to be
done from the beginning; nothing here prepares for it.

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

1. **Ask first** (draft below) and run it after a written yes. No cost; fits a student
   project; the answer also settles the questions for publication and a free public service.
2. **Publish the project under AGPL-3.0 first** (strategy A): then the test is an evaluation
   in an open-source environment, which the free column lists. Needs contributor rights
   confirmed and the owner's explicit approval (section 4); not automatic.
3. **Run it on the licence text alone**, accepting that Ultralytics' pages do not agree.
   This is a risk the owner would be taking knowingly, not a cleared path.
4. Buy Ultralytics' single-project R&D licence. Listed for completeness: a commercial
   licence is not an objective of this project, and nothing is purchased without the
   owner's separate approval.

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

Fill in the bracketed parts. Send from the person who runs the project (the owner, or the
student as author). Each draft describes AquaTrack as it is: a permanently free,
noncommercial student research and educational project. They ask about private research,
open-source publication and a free public application, and say plainly that there are no
commercial plans.

### 8.1 Ultralytics

**Route:** the licensing form on https://www.ultralytics.com/license (the page says they
reply within 24 hours). The form asks for: first and last name, **business email**, company
size, **company website**, industry (the list includes Education), and a free-text use case
(up to 5,000 characters). There is no field for an individual or a student project, so say
so in the text; a school email and the school's website are the accurate answers. The
page's fallback address is license@ultralytics.com; staff name the Contact form (topic
"Licensing") as the alternative.

**Use-case text / email:**

> Subject: Licensing question from a free, noncommercial student project using YOLO11m
>
> Hello,
>
> I am writing about AquaTrack, a swimming-technique analysis web application. It is a
> permanently free, noncommercial student research and educational project [by NAME, with
> TEACHER/INSTITUTION]. It is not a company, has no revenue, and will never charge users,
> sell subscriptions or carry advertising. The repository is currently private.
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
> 1. Private research. May we run a one-off, private, noncommercial technical evaluation of
>    the unmodified package and weights on a cloud GPU (one public test video, no users, no
>    service offered) under AGPL-3.0 while the repository is still private?
> 2. Privately hosted proof of concept. May a student-developed application use the
>    pretrained model in a privately hosted proof of concept with no public access, under
>    AGPL-3.0?
> 3. Open-source publication. If we publish the project under AGPL-3.0, which parts must be
>    published: the inference worker only, the whole backend, the separate web frontend?
> 4. Free public application. If the complete project is published under AGPL-3.0, is that
>    sufficient to operate it as a free, public, noncommercial web application? Is anything
>    further required, for example how users are offered the source?
> 5. ONNX. If we exported `yolo11m.pt` to ONNX and ran it with ONNX Runtime, without your
>    package at run time, would any of the answers above change?
> 6. Academic terms. Is there an academic, educational, student or evaluation arrangement
>    that would apply to a project like this?
> 7. Notices. Which copyright, licence and attribution notices must we retain or display?
>
> We have no commercial plans and are not seeking a commercial licence. We have not
> deployed the application and will not use the model beyond what you confirm.
> Thank you for your help.
>
> [NAME, ROLE, CONTACT]

### 8.2 OpenMMLab / MMPose maintainers and the RTMW authors

**Routes:** no licensing or business contact is published. What is published: GitHub
issues on https://github.com/open-mmlab/mmpose (an existing open issue, #3278, asks about
RTMW cocktail14 weights and is unanswered; adding to it may be more useful than a new
issue); the authors' addresses printed on the RTMW paper (arXiv 2407.08634: Tao Jiang,
Xinchen Xie, Yining Li, Shanghai AI Laboratory); the package contact openmmlab@gmail.com in
MMPose's `setup.py`. A GitHub issue is public: leave out the name and contact line there.

> Subject: Usage terms of the RTMW-x cocktail14 checkpoint for a free, noncommercial student project
>
> Hello,
>
> Thank you for MMPose and RTMW. I am writing about AquaTrack, a swimming-technique analysis
> application. It is a permanently free, noncommercial student research and educational
> project; it will never charge users or be offered commercially. We use exactly one of
> your released models:
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
> which are for research or noncommercial use only. Could you tell us:
>
> 1. Under what licence or terms is this checkpoint released? Is it covered by the
>    repository's Apache-2.0 licence?
> 2. Private research. Is private, noncommercial, research-only evaluation of it on a GPU
>    permitted?
> 3. May a student-developed application use it in a privately hosted proof of concept?
> 4. Open-source publication. If we publish our project's source, what must we do regarding
>    the checkpoint? We would not include the weights or our ONNX file; users would download
>    the checkpoint from your host and convert it themselves.
> 5. Free public application. May it be used in a free, public, noncommercial web
>    application run by a student project?
> 6. Does converting it to ONNX change any of these conditions?
> 7. Which copyright, licence or citation notices should we retain or display?
>
> We have no commercial plans. We understand you may not be able to speak for the dataset
> owners; your own position as the publisher of the checkpoint would already help us a
> great deal.
>
> Thank you.
>
> [NAME, ROLE, CONTACT]

### 8.3 COCO-WholeBody rights holders

**Route:** the dataset's README (https://github.com/jin-s13/COCO-WholeBody, "Terms of Use",
item 2) names a contact, with a second person in copy. It is given there for commercial
usage; it is the only contact published, so it is also where to ask whether a noncommercial
use is within the terms. Use the addresses exactly as printed there. Note for the owner: the
README's text names CC BY 4.0 while its link points to CC BY-NC 4.0; question 1 asks about
that.

> Subject: Noncommercial student project using a third-party model trained partly on COCO-WholeBody
>
> Dear Mr. Malon, dear Dr. Jin,
>
> I am writing about AquaTrack, a swimming-technique analysis application. It is a
> permanently free, noncommercial student research and educational project; it will never
> charge users or be offered commercially. We do not use, hold or redistribute the
> COCO-WholeBody dataset or its annotations. We use a pretrained model published by
> OpenMMLab MMPose,
> `rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth`, whose model card
> lists COCO-WholeBody as one of fourteen training datasets. We run it for inference only,
> server side, converted to ONNX, and we do not redistribute it.
>
> Your Terms of Use state that the dataset is only for research and noncommercial use. We
> would like to be sure our use is within them and ask:
>
> 1. Which licence applies to the annotations: CC BY 4.0, as the README text says, or
>    CC BY-NC 4.0, as its link indicates?
> 2. Do your terms apply to the use of a third-party model that was trained partly on
>    COCO-WholeBody, when the user has no access to the dataset?
> 3. Private research. Is private, noncommercial, research-only evaluation of such a model
>    within your terms?
> 4. Open-source publication. If we publish our own source code (without the model weights
>    and without any COCO-WholeBody data), does anything in your terms apply?
> 5. Free public application. Is use of such a model in a free, public, noncommercial web
>    application run by a student project within your terms?
> 6. Does converting the model to ONNX change anything?
> 7. Which notices or citations should we retain or display?
>
> We have no commercial plans and are not asking for a commercial licence.
>
> Thank you for your time.
>
> [NAME, ROLE, CONTACT]

## 9. Decisions for the owner

Decided (2026-11-16): AquaTrack is permanently free and noncommercial. Reported by the
owner (2026-11-16): permission from Ultralytics and the relevant RTMW-x parties; its written
scope is not yet reviewed (section 0.1). Still open:

0. Provide the written confirmations so the table in section 0.1 can be filled in.

1. Detector route: open-source under AGPL-3.0 (the fitting one), or a replacement if the
   terms force it. A paid licence is not an objective.
2. If AGPL-3.0: confirm contributor rights (section 4) and give explicit approval before
   any licence file is added or the repository is made public. Neither happens automatically.
3. The private GPU test: which of the ways in section 6.
4. May the drafts in section 8 be sent, and by whom (the owner, or the student as author)?
5. Is legal review wanted before a free public application is opened to users?

Until these are answered: no licence file, no publication, no change of visibility, no
public deployment, no inquiry sent, no purchase.
