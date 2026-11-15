# Evidence library (version 2026.11-1)

Code: `src/aquatrack/evidence.py`. Used by `src/aquatrack/analysis/feedback.py` (general
information per goal, and the "why it may matter" text of a focus) and never by a rule.

## How sources were admitted

1. A candidate paper was looked up **by DOI at Crossref**; title, authors, year and journal had
   to match.
2. Its **abstract was read at PubMed**. Only abstracts were read, not full texts. Every claim in
   the library is limited to what the abstract states, reworded.
3. Anything that failed either step was left out.

Verified on 2026-11-15. The lookup scripts are local research tools
(`experiments/phase4_evidence/`, not committed).

Why the check matters: three DOIs first written down from memory were wrong. One resolved to an
unrelated paper on knee torque curves, two did not resolve at all. The correct records were then
found by title search and are the ones in the library.

## Sources (10)

| Id | Reference | Kind | Studied |
| --- | --- | --- | --- |
| chollet2000 | Chollet, Chalies, Chatard (2000). A New Index of Coordination for the Crawl: Description and Usefulness. Int J Sports Med 21(1):54-59. doi:10.1055/s-2000-8855 | study | 43 swimmers, three performance levels |
| seifert2004 | Seifert, Chollet, Bardy (2004). Effect of swimming velocity on arm coordination in the front crawl: a dynamic analysis. J Sports Sci 22(7):651-660. doi:10.1080/02640410310001655787 | study | 14 elite men |
| seifert2007 | Seifert, Chollet, Rouard (2007). Swimming constraints and arm coordination. Hum Mov Sci 26(1):68-86. doi:10.1016/j.humov.2006.09.003 | study | 42 swimmers (elite men, mid-level men, elite women) |
| schnitzler2010 | Schnitzler, Seifert, Alberty, Chollet (2010). Hip Velocity and Arm Coordination in Front Crawl Swimming. Int J Sports Med 31(12):875-881. doi:10.1055/s-0030-1265149 | study | 22 swimmers, elite and recreational |
| figueiredo2012 | Figueiredo, Seifert, Vilas-Boas, Fernandes (2012). Individual profiles of spatio-temporal coordination in high intensity swimming. Hum Mov Sci 31(5):1200-1212. doi:10.1016/j.humov.2012.01.006 | study | 10 competitive men |
| seifert2014 | Seifert, Komar, Barbosa, Toussaint, Millet, Davids (2014). Coordination Pattern Variability Provides Functional Adaptations to Constraints in Swimming Performance. Sports Med 44(10):1333-1345. doi:10.1007/s40279-014-0210-x | review | coordination studies |
| zamparo2009 | Zamparo, Gatta, Pendergast, Capelli (2009). Active and passive drag: the role of trunk incline. Eur J Appl Physiol 106(2):195-205. doi:10.1007/s00421-009-1007-8 | study | competitive swimmers |
| cortesi2015 | Cortesi, Gatta (2015). Effect of The Swimmer's Head Position on Passive Drag. J Hum Kinet 49(1):37-45. doi:10.1515/hukin-2015-0106 | study | 10 regional-level men |
| psycharakis2010 | Psycharakis, Sanders (2010). Body roll in swimming: A review. J Sports Sci 28(3):229-236. doi:10.1080/02640410903508847 | review | body roll studies |
| barbosa2010 | Barbosa, Bragada, Reis, Marinho, Carvalho, Silva (2010). Energetics and biomechanics as determining factors of swimming performance: Updating the state of the art. J Sci Med Sport 13(2):262-269. doi:10.1016/j.jsams.2009.01.003 | review | competitive swimming research |

No full text is stored in the repository. Abstracts are not copied; claims are in our own words.

## Left out, and why

| Candidate | Why it is not in the library |
| --- | --- |
| Craig and Pendergast (1979), stroke rate, distance per stroke and velocity | Crossref record found (doi:10.1249/00005768-197901130-00011); no abstract available to read, so no claim could be checked |
| Wulf (2013), attentional focus and motor learning | Crossref record found (doi:10.1080/1750984X.2012.723728); no abstract available. Nothing on motor learning is in the library, so feedback gives no advice on how to practise |
| A paper on the accuracy of video-based swimming kinematics | Not found by title; measurement limits are therefore stated as our own, not as research |

## Kinds of claim

| Kind | Count | Meaning |
| --- | --- | --- |
| scientific_finding | 10 | Reported in the abstract of a source above |
| research_supported | 1 | A practical reading that follows from findings (compare like with like) |
| engineering_heuristic | 1 | AquaTrack's own rule; no study behind the numbers |
| unverified_hypothesis | 1 | Something AquaTrack assumes and has not checked |

Each claim records the context it was found in, what the study measured, which AquaTrack metrics
it touches, its `applicability` (how far it is from what AquaTrack measures) and its limitations.

## What the evidence does and does not support

- Stroke rate, coordination and body position change with swimming pace (chollet2000,
  seifert2004, seifert2007, zamparo2009). **Supports:** comparing swims only at a similar effort.
  **Does not support:** any target stroke rate or body angle for an individual.
- There is no single ideal coordination pattern; variation can be functional (seifert2014).
  **Supports:** not treating variation as a fault. **Does not support:** any threshold for how
  much cycle-time variation matters.
- Trunk incline relates to frontal area and drag in competitive swimmers (zamparo2009); head
  position changes passive drag in a towed glide (cortesi2015). **Supports:** explaining why body
  and head position are worth noticing. **Does not support:** judging AquaTrack's picture angles,
  which have not been checked against those measurements; nor swimmers other than those studied.
- Most sources studied competitive or elite adults. None is specific to beginners or children.

## Review of the inactive interpretation rules

| Rule | Interpretation it would make | Evidence found | Same measurement, population, conditions? | Decision |
| --- | --- | --- | --- | --- |
| pending.body_line_direction | "Your body or leg line is too steep / improved" | zamparo2009: trunk incline falls with speed and relates to drag | No. Trunk incline measured during controlled-speed swimming vs. an unvalidated picture angle; competitive swimmers; no threshold; speed not measured by AquaTrack | **Stays inactive.** Body position is described and compared with the swimmer's own swims; the finding is shown as general information for the body-alignment goal |
| pending.head_position | "Your head is too high" | cortesi2015: head up raises passive drag | No. Passive towing under water vs. swimming at the surface; AquaTrack's head measure mixes in shoulder roll | **Stays inactive.** General information only |
| pending.stroke_rate_for_distance | "Your stroke rate is too high / low for this distance" | chollet2000, seifert2004, seifert2007: rate changes with pace | No. Needs swim speed or stroke length, which AquaTrack does not measure; group data, no individual targets | **Stays inactive.** General information only |
| pending.arm_pull | "Your elbow drops / pull is too shallow" | None admitted on elbow angle or pull depth | Not applicable; and Phase 2 arm points are unresolved | **Stays inactive.** No arm judgement |
| timing.uneven_rhythm (active) | "Several cycles were off your own rhythm; worth a look" | seifert2014 cautions against reading variation as a fault | The rule compares the swimmer with their own median, not a norm | **Unchanged.** Still an engineering heuristic; its wording now cites the caution |

No rule was activated in Phase 4.
