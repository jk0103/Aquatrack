# Form measures and standard: status and next steps (2026-11-25)

Branch `claude/project-thread-u1qeau`. Today was research and planning. The only file added is
this report; no measure was changed or added. Tests on this state: 597 passed, 2 skipped, 2 failed
(`tests/test_queue.py`; both failed before this branch's work too).

## What we did

1. **Tried a catch rule and removed it.** It flagged a forearm 20 degrees or more from straight
   down. The cut-off was our own, and no source we could read gives a best catch angle. The metric
   `catch_forearm_angle` stays, for information only.
2. **Rechecked the catch measurements.** The arm was drawn on all 38 catch frames of five local
   clips. The points follow the arm, with a visible forearm offset in a few Wellbrock frames.
3. **Read research and coaching guides** (mostly abstracts). Main points:
   - Body position: the strongest support. Less trunk tilt goes with less drag
     ([Zamparo 2009](https://doi.org/10.1007/s00421-009-1007-8),
     [Zamparo 1996](https://doi.org/10.1007/bf02425476)).
   - Head in line with the body: guides agree; one towing study supports it
     ([Cortesi 2015](https://doi.org/10.1515/hukin-2015-0106)).
   - Elbow in the pull: a dropped elbow was the most common error graded by people from video
     ([Virag 2014](https://doi.org/10.1177/1941738114527056)). An elbow-height index correlated with
     speed in 16 skilled men ([Suito 2017](https://doi.org/10.1080/02640414.2016.1221517)).
   - Arm timing: no ideal pattern ([Silva 2022](https://doi.org/10.1080/14763141.2022.2125428)). It
     changes with pace ([Seifert 2004](https://doi.org/10.1080/02640410310001655787)).
   - Sprint and distance specialists differed little
     ([McCabe 2011](https://doi.org/10.1080/02640414.2010.523090),
     [McCabe 2012](https://doi.org/10.1080/02640414.2012.660186)).
   - Safety: large inward shoulder rotation in the pull goes with higher shoulder impingement risk
     ([Yanai and Hay 2000](https://doi.org/10.1097/00005768-200001000-00006)). Do not add a "higher
     elbow" cue without care.
   - Not found: a verified number for judging a swimmer from a 2D side view, or ranges per level
     (beginner, hobby, masters, competitive).
4. **Found clips** for our own reference values (below).

## Decisions by the owner

- Measures: body line and hips, head position, elbow in the pull, kick, stroke rate, and arm
  timing only when detection allows it. No distance per stroke.
- Make our own reference values from 5 to 10 elite sprint and 5 to 10 elite distance clips, run
  through the detection model. Settle this before coding the measures.

## Clips

Checked on three preview frames each, not whole videos. Levels are from titles and general
knowledge and need checking. The clips are copyrighted: keep them out of git and the app, for
private testing only. YouTube's terms limit downloading.

Sprint:

| Swimmer | Best quality seen | View |
| --- | --- | --- |
| [Khloptsov, 50 free](https://www.youtube.com/watch?v=CoWdC-yueVE) | 1080p | Side, best one; elite level not verified |
| [Borges](https://www.youtube.com/watch?v=EfPeWPBtEPc) | 240p | Side |
| [Scherer](https://www.youtube.com/watch?v=DLJM-iwfcP8) | 240p | Side |
| [Delaroli](https://www.youtube.com/watch?v=2MdJJcU1HmY) | 240p | Side |
| [Nystrand](https://www.youtube.com/watch?v=k0gtwQxdXCU) | 240p | Mostly side, many bubbles |
| [Popov](https://www.youtube.com/watch?v=cBMrtiEE0uo) | 480p | Partly side, body cropped |
| [Trickett](https://www.youtube.com/watch?v=ImUoJ30TWKU) | 480p | Partly side, slow motion |

Distance (400 m and longer):

| Swimmer | Best quality seen | View |
| --- | --- | --- |
| [Wellbrock](https://www.youtube.com/watch?v=GvnoklPZaEU) | 720p | Side, already analysed locally; looks like a swimming tank |
| [Ledecky](https://www.youtube.com/watch?v=2ZRGwoOZmkw) | 1080p | Near side |
| [Sun Yang](https://www.youtube.com/watch?v=sRs5ryGT82w) | 720p | Near side, parts only |
| [Horton](https://www.youtube.com/watch?v=690pgWmvyZw) | 720p | Side for part |
| [Bennett](https://www.youtube.com/watch?v=z8NplL6Jf1Y) | 360p | Side, 10 s |
| [Laure Manaudou](https://www.youtube.com/watch?v=EZVESCiWctA) | 360p | Near side, slow motion |
| [Mellouli](https://www.youtube.com/watch?v=wCYRZ4VgQ9U) | 480p | Near side, slow motion |
| [Thorpe](https://www.youtube.com/watch?v=-8egC7PbOME) | 480p | Angled, about quarter speed |

## Next steps

1. Get the clips at the highest quality. Start with Khloptsov (1080p), Borges, Ledecky, Sun Yang
   and Horton. If 240p is too blurry for the pose model, find other sprint clips.
2. Decide where the pose model runs. `CLAUDE.md` says no heavy inference on the owner's Mac; Colab
   is the default. Not decided yet.
3. Keep only side-on, real-speed stretches. Slow motion cannot give stroke rate or timing.
4. Write one definition per measure, then report values per swimmer: middle value, spread, number
   of cycles, camera view. Keep sprint and distance apart.
5. Check points by drawing them on frames. `CleanPose.image_points()` is 0 to 1: multiply by the
   frame width and height.
6. Build one measure at a time: body line, head, elbow, kick, stroke rate, arm timing. Check each
   on real clips before the next.

Known problems for those steps:

- Level reference: pool lines moved 12 and 18 degrees in two clips. Find out whether that is real
  camera tilt (then it is correct) or an error.
- Head: the model's face points were about 0.08 trunk lengths off on SWIM-360, more than the 0.05
  now counted as a difference.
- Arm timing: the far arm's push is hidden. The spacing of the two arms' mid-pulls was about half
  a cycle in all four clips tested, so it does not separate swimmers. The idea to test: pulling
  share of the near arm minus that spacing.
- Kick code exists but has never been checked against video.
- A small group shows what these swimmers do, not what is best. It is not a verified standard.

## Corrections needed in files already pushed

Done locally on 2026-11-27 on `feature/aquatrack-production` (reference 2026.11-2; not
committed at the time of writing): the three items below were corrected in
`analysis/reference.py`, `REFERENCE_SWIMMERS.md` and `BIOMECHANICS_METRICS.md`. Still open: the
name "strong swimmers" itself is unverified for two of the three clips, and the clips'
copyright and download terms (see "Clips" above) apply to the numbers shown from them.

- `analysis/reference.py` and `REFERENCE_SWIMMERS.md`: descriptions such as "easy swim", "coach,
  not an elite racer" and "adult men" were guesses. So was the claim that Wellbrock's clip is cut
  from several passes.
- `BIOMECHANICS_METRICS.md`: "checked by eye" was not true when written. It has been done since
  (point 2 above); the corrected text is not committed yet.
- `REFERENCE_SWIMMERS.md` says no new model run was needed. That is true only for the
  re-measuring: the saved pose came from local model runs on 2026-11-11.
