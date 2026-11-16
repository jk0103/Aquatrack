# Training and calendar (training 1.0, library 2026.11-1)

Code: `src/aquatrack/training/` (`models.py` contracts, `library.py` activities and sources,
`planner.py` the planner, `explain.py` the check on optional rewording),
`src/aquatrack/api/training.py` (storage, ownership, edit rules, calendar), routes in
`src/aquatrack/api/main.py`. Screens: Training, Calendar, and the training cards on Home and
Progress.

Nothing here needs a language model, a video or pose data. A plan is a suggestion the swimmer
reviews, edits and schedules. It is never a prescription, and nothing in it has been shown to
improve anyone's swimming.

## 1. Two kinds of recommendation, never mixed

| Label | When | What it may say |
| --- | --- | --- |
| Analysis-based | The swimmer's newest analysed video has a stored finding shown as a focus or priority, and that finding's rule is in `RULE_ACTIVITIES` | "Your latest analysis found something worth a look ... It is not a confirmed fault." Carries the finding id, video id and analysis id |
| Goal-based | The swimmer chose goals and there is no such finding | "You chose X as a goal ... it does not mean AquaTrack found a problem in your swimming." |
| General | No goals chosen | A conservative general practice, labelled as such |

- Only two rules are mapped (`timing.uneven_rhythm`, `history.rhythm_less_steady`): the only
  issue rules that are active. Pending rules, observations, arm metrics and limited or
  unavailable metrics can never reach a plan (tested).
- The analysis state is read from what is stored (`none`, `unavailable`, `no_supported_issue`,
  `supported`); nothing is recomputed. On the two real clips it is `no_supported_issue`, so
  real users today get goal-based plans, and the plan says nothing is a correction.
- Every recommendation records: basis, activity, reason, inputs used, finding ids, sources,
  evidence class, what the swimmer can notice, what a later video can measure, assumptions and
  limitations.

## 2. Preferences

Stored on the swimmer's own profile (`profiles/{uid}`), written by the web app under the
security rules. Reused, never duplicated: `swim_level`, `sessions_per_week`, `minutes_per_day`
(the time available for a session), `goals`, `primary_goal`, `age`. New optional map
`training`: `days`, `time_of_day`, `typical_distance_m`, `strokes`, `equipment`, `difficulty`.
No medical or health information is asked for, and the rules refuse any other key.

Missing answers stay missing: the planner lists them (`missing`) and uses cautious defaults
that the plan names (30 minutes, 2 sessions, beginner, easy). A personal best never changes
the assumed level.

## 3. Activity library

14 activities, 13 active. Each has an id, category, levels, purpose, instructions, a minutes
range, intensity, rest, equipment, goals, related metrics and rules, what to notice, what a
later video can measure, safety lines, an evidence class, sources and limitations.

| Evidence class | Meaning | Activities |
| --- | --- | --- |
| Research-supported practice | a review in the library supports the practice (not the dose) | warm-up |
| Coaching guidance | described on a named coaching body's page that was read | still head, kick on your side, kickboard breathing, regular breathing rhythm |
| General suggestion | conservative common practice with no source behind it | count your strokes, even-effort repeats, catch-up, the main sets, cool-down |
| Unverified | not checked: never used | fingertip drag (inactive) |

Sources (checked 2026-11-16):

| Source | Kind | How checked | What is taken from it |
| --- | --- | --- | --- |
| Neiva et al., Sports Med 44:319-330, doi:10.1007/s40279-013-0117-y | review | Crossref + PubMed abstract | warm-up is widely used; evidence in swimming is mixed; its 1,000 to 1,500 m recommendation is for competition and is not used |
| McGowan et al. 2015, Sports Med 45:1523-1546, doi:10.1007/s40279-015-0376-x | review | Crossref + PubMed abstract | what an active warm-up does; practice grew largely from experience |
| Van Hooren & Peake 2018, Sports Med 48:1575-1595, doi:10.1007/s40279-018-0916-2 | review | Crossref + PubMed abstract | active cool-downs are largely ineffective for most recovery markers: the cool-down is described only as a calm end to a session |
| McGibbon et al. 2018, Sports Med 48:1621-1633, doi:10.1007/s40279-018-0901-9 | systematic review | Crossref + PubMed abstract | even pacing matters in races; says nothing about practice repeats |
| Swim England, "Improving your front crawl technique" (2018) | coaching page | page fetched and read | head and body position guidance |
| Swim England, "Front crawl breathing drills" (2018) | coaching page | page fetched and read | kickboard breathing, breathing every three strokes. Its first drill (staying under while breathing out for longer) is deliberately not used |
| U.S. Masters Swimming, "Freestyle Kick" guide (A. Sheaff) | coaching page | page fetched and read | kicking on the side works on body position and alignment |
| U.S. Masters Swimming, "The 5 Best 30-minute Swim Workouts" (H. Topper, 2026) | coaching page | page fetched and read | warm-up, drills, main set, cool-down as the shape of a session; 1,000 to 1,500 yards per 30 minutes as an upper reference |

Limits: research was read as abstracts only. Coaching pages were read through an automated
page fetch, not by a person, and are guidance, not evidence. Checked and left out: Wulf 2013,
Freudenheim et al. 2010 and Stoate & Wulf 2011 on attentional focus (records found, no abstract
available, so nothing about how to focus is claimed); Toubekis et al. 2008 (active recovery
between maximal 100 m efforts in 17-year-old competitive swimmers: not applicable); the Red
Cross / USA Swimming / YMCA statement on hypoxic blackout (the document could not be fetched,
so it is not cited; the ban on breath-holding practice is a product rule and needs no source).

## 4. Planner rules (all engineering choices)

- Session time = the swimmer's minutes, never more; capped by level (beginner 45, hobby 60,
  masters and competitive 90; under 18: 60; under 13: 45), minimum 15. Above the cap the plan
  fills the cap and says so.
- Shape: warm-up, technique blocks, main set, cool-down, split by fixed rules so the minutes
  always add up exactly (tested for every length from 15 to 90).
- Difficulty is the swimmer's choice, lowered where needed and never raised: unknown level or
  under 13 means easy; "challenging" needs masters or competitive level and an adult.
  Activities harder than the allowed difficulty are not offered. At most one brisk session a
  week, never the day after another, never for beginners, never all-out.
- Week: 7 days from the chosen start date, sessions only on available days, never more than
  the swimmer asked for, at most 6 (beginners 4), so there is always a day without swimming.
- Distance is a guide only ("about 5 x 50 m"), from assumed paces of 20 / 29 / 36 / 40 m per
  minute including rest by level, set at or below the coach article's range. With a typical
  distance set, repeats are trimmed to stay within it.
- History only rotates which practice comes first. It never raises the load. If more sessions
  were skipped than completed lately, the plan says so and keeps the swimmer's settings.
- Never in a plan: breath-holding or restricted breathing, all-out or exhaustive efforts,
  medical or injury advice, promises about times.

## 5. Storage and API

`training_plans/{id}` (one version of a plan) and `training_sessions/{id}` (one session).
Owner-read, no client writes: every change goes through the backend, which checks the owner
(someone else's session looks like a missing one) and validates the edit.

| Route | Does |
| --- | --- |
| `GET /training?today=` | preferences, analysis state, recommendations, library, active plans, week counts, upcoming, history |
| `POST /training/plans/preview` | generates a session or week; stores nothing |
| `POST /training/plans` | stores it; if the dates already hold a plan or session, answers with the conflict and stores nothing until `confirm` |
| `GET /training/calendar?start=&end=` | sessions and rest days in a range, and the swimmer's videos for linking |
| `POST /training/sessions` | a session the swimmer writes themself |
| `PATCH /training/sessions/{id}` | reschedule, retitle, change activities, skip, cancel, reopen |
| `POST /training/sessions/{id}/complete` | records completion: date, which activities, note, optional video link |
| `DELETE /training/sessions/{id}` | deletes one session; never touches a video |

- **Versions.** Replacing a week makes a new plan document (`version` + 1, same `series_id`);
  the old one is kept with status `replaced`. Completed, skipped and cancelled sessions always
  stay; sessions the swimmer edited stay unless they choose otherwise; untouched planned
  sessions are marked `replaced` and kept with the old version.
- **Edits.** Each activity is `recommended`, `modified` (the swimmer changed it) or `manual`
  (the swimmer added it, from the library or typed in). A typed-in activity is never shown as
  recommended and never sent to a model. Refused: unknown or inactive activities, activities
  above the swimmer's level or needing equipment they did not list, minutes outside an
  activity's range, the same activity twice, more than 180 minutes, two brisk sets, a brisk
  set without a warm-up, unreal dates and times.
- **Dates.** Local calendar dates ("YYYY-MM-DD") and optional local times, stored as typed and
  never converted between time zones. "Today" comes from the swimmer's device.
- **Completion** is recorded only when the swimmer says so. A date passing completes nothing.
- **Adherence is not technique.** Completed and skipped counts are shown as practice the
  swimmer recorded, apart from measured changes, and are never read as improvement. No text
  links a measured change to training.

## 6. Deleting a video

Before a video's data is deleted, every pointer to it in training data is removed: session
video links (flagged "has been deleted"), checkpoint links, and, for a plan that was based on
its analysis, the video and analysis ids, finding ids and finding titles. The sessions, notes
and completion history stay: deleting a video is not deleting training. Independently, a link
to a video that no longer exists is never returned by the API. Deleting a training session
never touches a video.

## 7. Optional rewording by OpenAI (off by default)

See `docs/FEEDBACK.md` for the adapter and configuration. For a plan, the model gets the
plan's structure (activity ids, the library's instructions, minutes, basis, level and goal
categories) and no identifiers, notes or typed-in activities. Its answer is rejected whole
if it: is not the requested structure; names an unknown or repeated session; uses a number
that is not in the plan; names an exercise, piece of equipment or library activity the plan
does not contain; mentions research or cites anything; promises results; gives unsafe or
medical advice; words a finding as a confirmed fault; or, for a goal-based or general plan,
says anything about what the swimmer's swimming is like. A rejected or failed answer leaves
the plan exactly as the planner wrote it. These checks are word patterns: they cannot catch
every unsupported sentence, and they have only been run against mocked answers.

## 8. Not validated

- No plan, activity, duration or pace here has been tested on swimmers. Synthetic fixtures
  and software tests show the rules are followed, not that training works.
- Analysis-based plans have only been exercised with synthetic findings: the real clips
  produce none.
- Level caps, pace assumptions, the session split and the weekly pattern are engineering
  choices. Age handling is general caution, not paediatric guidance.
- Still open: reminders, recurring plans beyond 7 days, component-level UI tests, a durable
  store for edits made at the same moment from two devices (last write wins).
