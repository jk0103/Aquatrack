"""A small, curated evidence library: verified sources and the claims taken from them.

Every source here was looked up by DOI at Crossref (title, authors, year, journal) and its
abstract was read at PubMed on the date recorded. **Only abstracts were read, not full
texts**, so every claim is limited to what the abstract states, in our own words. A source
whose record or abstract could not be checked is not in this file (see
docs/EVIDENCE_LIBRARY.md for the candidates that were left out and why).

Four kinds of statement are kept apart and are never shown as equally established:

  scientific_finding      reported by a study or review in the library
  research_supported      a practical reading that follows from such findings (a suggestion)
  engineering_heuristic   an AquaTrack design choice with no study behind the number
  unverified_hypothesis   something we assume and have not checked

A claim being in the library does not validate any AquaTrack metric or switch on any rule.
`applicability` says, per claim, how far it is from what AquaTrack measures.
"""
# ruff: noqa: E501  (statements and limitations are kept whole, one per line)

from typing import Literal

from pydantic import BaseModel

EVIDENCE_VERSION = "2026.11-1"
VERIFIED_ON = "2026-11-15"

ClaimKind = Literal[
    "scientific_finding", "research_supported", "engineering_heuristic", "unverified_hypothesis"
]


class EvidenceSource(BaseModel):
    id: str
    title: str
    authors: list[str]
    year: int
    journal: str
    volume: str = ""
    pages: str = ""
    doi: str
    pmid: str = ""
    kind: Literal["original_study", "review"]
    population: str
    methods: str
    verified_on: str = VERIFIED_ON
    verified_via: str = "Crossref record by DOI; abstract read at PubMed"
    read: Literal["abstract"] = "abstract"  # full texts were not read

    @property
    def url(self) -> str:
        return f"https://doi.org/{self.doi}"

    @property
    def citation(self) -> str:
        names = self.authors if len(self.authors) <= 3 else [self.authors[0], "et al."]
        where = (
            f"{self.journal}"
            + (f" {self.volume}" if self.volume else "")
            + (f":{self.pages}" if self.pages else "")
        )
        return f"{', '.join(names)} ({self.year}). {self.title}. {where}."


class Claim(BaseModel):
    id: str
    kind: ClaimKind
    source_id: str | None  # None for heuristics and hypotheses
    statement: str  # in our words, no more than the abstract supports
    context: str  # who and what conditions it was found for
    measurement_requirements: str  # what the study measured, and how
    metric_keys: list[str] = []  # AquaTrack metrics it touches, if any
    topics: list[str] = []  # goal keys it can inform
    applicability: str  # how far it is from AquaTrack's own measurements
    limitations: list[str] = []


def _src(**kw) -> EvidenceSource:
    return EvidenceSource(**kw)


SOURCES: dict[str, EvidenceSource] = {
    s.id: s
    for s in [
        _src(
            id="chollet2000",
            title="A New Index of Coordination for the Crawl: Description and Usefulness",
            authors=["Chollet D", "Chalies S", "Chatard JC"],
            year=2000,
            journal="International Journal of Sports Medicine",
            volume="21(1)",
            pages="54-59",
            doi="10.1055/s-2000-8855",
            pmid="10683100",
            kind="original_study",
            population="43 swimmers in three performance-level groups",
            methods="Video analysis of stroke phases and arm and leg coordination at paces for 800 m, 100 m and 50 m",
        ),
        _src(
            id="seifert2004",
            title="Effect of swimming velocity on arm coordination in the front crawl: a dynamic analysis",
            authors=["Seifert L", "Chollet D", "Bardy BG"],
            year=2004,
            journal="Journal of Sports Sciences",
            volume="22(7)",
            pages="651-660",
            doi="10.1080/02640410310001655787",
            pmid="15370496",
            kind="original_study",
            population="14 elite male front-crawl swimmers",
            methods="Eight swim trials at increasing target velocity; velocity, stroke rate, stroke length and arm phases from video",
        ),
        _src(
            id="seifert2007",
            title="Swimming constraints and arm coordination",
            authors=["Seifert L", "Chollet D", "Rouard A"],
            year=2007,
            journal="Human Movement Science",
            volume="26(1)",
            pages="68-86",
            doi="10.1016/j.humov.2006.09.003",
            pmid="17126942",
            kind="original_study",
            population="42 swimmers: 15 elite men, 15 mid-level men, 12 elite women",
            methods="Seven self-paced 25 m trials simulating race paces from 1500 m to maximal; velocity, stroke rate, stroke length and arm phases from video",
        ),
        _src(
            id="schnitzler2010",
            title="Hip Velocity and Arm Coordination in Front Crawl Swimming",
            authors=["Schnitzler C", "Seifert L", "Alberty M", "Chollet D"],
            year=2010,
            journal="International Journal of Sports Medicine",
            volume="31(12)",
            pages="875-881",
            doi="10.1055/s-0030-1265149",
            pmid="21072734",
            kind="original_study",
            population="22 swimmers in an elite and a recreational group",
            methods="Four trials at paces relative to each swimmer's maximum; hip velocity from a velocity meter, coordination from video",
        ),
        _src(
            id="figueiredo2012",
            title="Individual profiles of spatio-temporal coordination in high intensity swimming",
            authors=["Figueiredo P", "Seifert L", "Vilas-Boas JP", "Fernandes RJ"],
            year=2012,
            journal="Human Movement Science",
            volume="31(5)",
            pages="1200-1212",
            doi="10.1016/j.humov.2012.01.006",
            pmid="22921924",
            kind="original_study",
            population="10 male competitive swimmers",
            methods="200 m front crawl at race pace filmed by two above-water and four underwater cameras; 3D reconstruction of arm coupling in each 50 m lap",
        ),
        _src(
            id="seifert2014",
            title="Coordination Pattern Variability Provides Functional Adaptations to Constraints in Swimming Performance",
            authors=["Seifert L", "Komar J", "Barbosa T", "Toussaint H", "Millet G", "Davids K"],
            year=2014,
            journal="Sports Medicine",
            volume="44(10)",
            pages="1333-1345",
            doi="10.1007/s40279-014-0210-x",
            pmid="24895244",
            kind="review",
            population="Review of studies on inter-limb coordination in swimming",
            methods="Narrative overview within an ecological dynamics framework",
        ),
        _src(
            id="zamparo2009",
            title="Active and passive drag: the role of trunk incline",
            authors=["Zamparo P", "Gatta G", "Pendergast D", "Capelli C"],
            year=2009,
            journal="European Journal of Applied Physiology",
            volume="106(2)",
            pages="195-205",
            doi="10.1007/s00421-009-1007-8",
            pmid="19224240",
            kind="original_study",
            population="Competitive swimmers",
            methods="Active drag at 0.6 to 1.4 m/s with trunk incline and projected frontal area; comparison with passive towing",
        ),
        _src(
            id="cortesi2015",
            title="Effect of The Swimmer's Head Position on Passive Drag",
            authors=["Cortesi M", "Gatta G"],
            year=2015,
            journal="Journal of Human Kinetics",
            volume="49(1)",
            pages="37-45",
            doi="10.1515/hukin-2015-0106",
            pmid="26839604",
            kind="original_study",
            population="10 male regional-level swimmers with at least 10 years of competitive experience",
            methods="Passive towing 60 cm under water at 1.5, 1.7 and 1.9 m/s, in two arm positions and three head positions",
        ),
        _src(
            id="psycharakis2010",
            title="Body roll in swimming: A review",
            authors=["Psycharakis SG", "Sanders RH"],
            year=2010,
            journal="Journal of Sports Sciences",
            volume="28(3)",
            pages="229-236",
            doi="10.1080/02640410903508847",
            pmid="20131140",
            kind="review",
            population="Review of the swimming literature on body roll",
            methods="Critical narrative review",
        ),
        _src(
            id="barbosa2010",
            title="Energetics and biomechanics as determining factors of swimming performance: Updating the state of the art",
            authors=["Barbosa TM", "Bragada JA", "Reis VM", "Marinho DA", "Carvalho C", "Silva AJ"],
            year=2010,
            journal="Journal of Science and Medicine in Sport",
            volume="13(2)",
            pages="262-269",
            doi="10.1016/j.jsams.2009.01.003",
            pmid="19409842",
            kind="review",
            population="Review of competitive swimming research",
            methods="Narrative state-of-the-art review",
        ),
    ]
}

NOT_MEASURED = "AquaTrack does not measure this."

CLAIMS: dict[str, Claim] = {
    c.id: c
    for c in [
        Claim(
            id="coordination_changes_with_pace",
            kind="scientific_finding",
            source_id="chollet2000",
            statement="In front crawl, the share of the stroke spent in propulsive phases and the timing between the two arms' pulls changed as swimmers went from an 800 m pace to a 50 m pace, and differed between performance levels.",
            context="43 swimmers of three performance levels, at 800 m, 100 m and 50 m paces",
            measurement_requirements="Start and end of each arm's propulsive phases, from underwater video of both arms",
            metric_keys=["stroke_rate", "cycle_duration"],
            topics=["arm_technique", "speed", "overall_freestyle"],
            applicability="Supports comparing swims only at a similar pace. The coordination index itself needs both arms' pull phases, which AquaTrack cannot follow from one side view.",
            limitations=[
                "Group averages; no value is given that an individual should aim for.",
                "The index of coordination is not something AquaTrack measures.",
            ],
        ),
        Claim(
            id="coordination_mode_switches_with_speed",
            kind="scientific_finding",
            source_id="seifert2004",
            statement="Elite male swimmers changed their arm coordination pattern as speed rose, switching from a pattern with a gap between the arms' pulls to one without a gap at around their 100 m pace.",
            context="14 elite male front-crawl swimmers, from 3000 m pace to maximal speed",
            measurement_requirements="Swim velocity, stroke rate, stroke length and arm phases from video",
            metric_keys=["stroke_rate"],
            topics=["speed", "arm_technique"],
            applicability="Another reason a sprint and an easy swim are not compared. Found in elite men; not shown here for other swimmers.",
            limitations=[
                "Elite adult men only.",
                "Needs swim velocity and both arms' phases, which AquaTrack does not measure.",
            ],
        ),
        Claim(
            id="stroke_rate_and_length_change_with_race_pace",
            kind="scientific_finding",
            source_id="seifert2007",
            statement="Stroke rate, stroke length and arm coordination all changed with race pace in elite men, mid-level men and elite women alike, with the change in coordination pattern at about the 200 m pace.",
            context="42 swimmers (elite men, mid-level men, elite women), 25 m trials at simulated race paces",
            measurement_requirements="Velocity, stroke rate and stroke length from video over a known distance",
            metric_keys=["stroke_rate", "cycle_duration"],
            topics=["speed", "stroke_consistency", "overall_freestyle"],
            applicability="Stroke rate is something AquaTrack measures, but the study describes how it moves with pace, not what rate is right for a swimmer. Without swim speed AquaTrack cannot place a clip on that scale.",
            limitations=[
                "Short 25 m simulations to avoid fatigue.",
                "No recreational or beginner swimmers.",
                "AquaTrack does not measure swim speed or stroke length.",
            ],
        ),
        Claim(
            id="no_single_ideal_coordination",
            kind="scientific_finding",
            source_id="seifert2014",
            statement="A review of swimming coordination argues that there is no single ideal coordination pattern that every swimmer should copy: skilled swimming balances a stable pattern with variation that adapts to the swimmer, the task and the conditions.",
            context="Review of inter-limb coordination studies across strokes and levels",
            measurement_requirements="Coordination between limbs across cycles and conditions",
            metric_keys=["rhythm_variation"],
            topics=["stroke_consistency", "overall_freestyle", "arm_technique"],
            applicability="Backs the choice not to treat variation between cycles as a fault by itself. It is about coordination between limbs, which is broader than the cycle-time variation AquaTrack measures.",
            limitations=[
                "A theoretical review, not a test of any threshold.",
                "Does not say how much variation in cycle time is useful or harmful.",
            ],
        ),
        Claim(
            id="speed_variation_within_stroke_differs_by_level",
            kind="scientific_finding",
            source_id="schnitzler2010",
            statement="Elite swimmers showed less variation of hip speed within the stroke cycle than recreational swimmers, and kept it stable across paces, while it rose with pace in the recreational group.",
            context="22 swimmers, elite and recreational, at four paces relative to their own maximum",
            measurement_requirements="Hip velocity within each cycle from a velocity meter attached to the swimmer",
            topics=["stroke_consistency", "speed", "endurance"],
            applicability=NOT_MEASURED
            + " It needs speed within the stroke, not cycle time. It is the closest verified evidence on steadiness and skill level, and it is about a different quantity.",
            limitations=[
                "A different kind of steadiness from cycle-to-cycle timing.",
                "Needs a velocity meter.",
            ],
        ),
        Claim(
            id="coordination_profiles_differ_and_change_with_fatigue",
            kind="scientific_finding",
            source_id="figueiredo2012",
            statement="Over a 200 m race-pace swim, competitive swimmers' biomechanical and coordination measures declined with fatigue, and the swimmers fell into different coordination profiles rather than one.",
            context="10 male competitive swimmers, 200 m front crawl at race pace",
            measurement_requirements="3D arm kinematics from six cameras, two cycles per 50 m lap",
            topics=["endurance", "arm_technique", "overall_freestyle"],
            applicability="Supports reading a change across a long swim with care and not expecting one profile for everyone. AquaTrack's short single-camera clips cannot reproduce the measurement.",
            limitations=[
                "Ten competitive men.",
                "Six-camera 3D analysis.",
                "AquaTrack clips cover a few seconds, not 200 m.",
            ],
        ),
        Claim(
            id="trunk_incline_falls_with_speed",
            kind="scientific_finding",
            source_id="zamparo2009",
            statement="In competitive swimmers, trunk incline and the body's frontal area presented to the water both got smaller as swimming speed increased, and drag at a given speed depended mainly on that frontal area.",
            context="Competitive swimmers at 0.6 to 1.4 m/s",
            measurement_requirements="Trunk incline and projected frontal area measured during active swimming at controlled speeds",
            metric_keys=["body_line_angle", "leg_line_angle"],
            topics=["body_alignment", "speed", "overall_freestyle"],
            applicability="Explains why body position matters and why it has to be compared at a similar speed. AquaTrack's body line is an angle in the picture from one camera; it has not been checked against the study's trunk incline, and the study gives no target angle.",
            limitations=[
                "Competitive swimmers at controlled speeds.",
                "No threshold for an individual.",
                "AquaTrack's angle is not validated against trunk incline.",
            ],
        ),
        Claim(
            id="head_position_changes_passive_drag",
            kind="scientific_finding",
            source_id="cortesi2015",
            statement="When swimmers were towed under water without moving, drag was lower with the head down or in line with the body than with the head up, by about 4 to 5% with the arms at the sides and about 10% with the arms stretched ahead.",
            context="10 male regional-level swimmers towed passively 60 cm under water at 1.5 to 1.9 m/s",
            measurement_requirements="Towing force in fixed glide positions",
            metric_keys=["head_height"],
            topics=["body_alignment", "overall_freestyle"],
            applicability="A reason head position is worth noticing. It was measured in a motionless glide under water, not while swimming at the surface, and AquaTrack's head measure has not been matched to the study's head positions.",
            limitations=[
                "Passive towing, not swimming.",
                "Ten experienced male swimmers.",
                "Says nothing about breathing or about how much to change.",
            ],
        ),
        Claim(
            id="body_roll_asymmetry_not_shown_to_affect_performance",
            kind="scientific_finding",
            source_id="psycharakis2010",
            statement="A review of body roll research reports that swimmers roll the shoulders more than the hips, and that asymmetries in roll exist in front crawl without evidence that they affect performance.",
            context="Review of body roll studies, mostly front crawl",
            measurement_requirements="Shoulder and hip roll angles, usually from multi-camera 3D analysis",
            topics=["body_alignment", "breathing", "overall_freestyle"],
            applicability=NOT_MEASURED + " Body roll cannot be seen from one side camera.",
            limitations=[
                "The review itself lists many open questions.",
                "Needs a front, overhead or multi-camera view.",
            ],
        ),
        Claim(
            id="performance_links_stroke_kinematics_and_energetics",
            kind="scientific_finding",
            source_id="barbosa2010",
            statement="A review of competitive swimming research describes swimming speed as tied to stroke length, stroke frequency and coordination on one side and to energy cost on the other.",
            context="Review of competitive swimming studies",
            measurement_requirements="Swim velocity, stroke length and frequency, and energy expenditure",
            metric_keys=["stroke_rate"],
            topics=["speed", "endurance", "overall_freestyle"],
            applicability="Background for why stroke rate alone does not say how well someone swims: speed and stroke length are needed too, and AquaTrack measures neither.",
            limitations=[
                "A broad overview; no values to apply to an individual.",
                "Competitive swimmers.",
            ],
        ),
        # ---- suggestions that follow from the findings above (not findings themselves)
        Claim(
            id="compare_like_with_like",
            kind="research_supported",
            source_id="seifert2007",
            statement="Because stroke rate, coordination and body position all shift with pace, a swimmer's clips are best compared when the distance, effort and filming are the same.",
            context="Follows from the pace effects reported in the coordination and drag studies in this library",
            measurement_requirements="Two clips of the same task",
            metric_keys=["stroke_rate", "body_line_angle"],
            topics=["overall_freestyle", "speed"],
            applicability="This is how AquaTrack already decides whether two swims may be compared.",
            limitations=[
                "A practical reading of the findings, not something a study tested as a rule."
            ],
        ),
        # ---- our own choices and assumptions, labelled as such
        Claim(
            id="heuristic_rhythm_thresholds",
            kind="engineering_heuristic",
            source_id=None,
            statement="AquaTrack calls a stroke cycle off the rhythm when it differs from the clip's middle cycle time by more than 3 video frames and 10%, and flags a clip when at least 3 cycles and a quarter of them do.",
            context="AquaTrack's own rule",
            measurement_requirements="Reliable cycle times for at least 6 cycles of one arm",
            metric_keys=["cycle_duration", "rhythm_variation"],
            topics=["stroke_consistency"],
            applicability="A design choice from timing resolution. No study in this library supports these numbers.",
            limitations=["Not validated against swimming speed, efficiency or coach assessment."],
        ),
        Claim(
            id="hypothesis_picture_angles_track_body_position",
            kind="unverified_hypothesis",
            source_id=None,
            statement="We assume that the body-line and head measures taken in the picture move in the same direction as the trunk incline and head positions studied in the drag research.",
            context="AquaTrack's own assumption",
            measurement_requirements="A comparison against a calibrated measurement, which has not been done",
            metric_keys=["body_line_angle", "leg_line_angle", "head_height"],
            topics=["body_alignment"],
            applicability="Until this is checked, body-position measurements are described and compared with the swimmer's own earlier swims, never judged.",
            limitations=[
                "Not tested.",
                "One camera, so perspective and body roll change the picture angle.",
            ],
        ),
    ]
}


def claims_for_topic(
    topic: str, kinds: tuple[str, ...] = ("scientific_finding", "research_supported")
) -> list[Claim]:
    return [c for c in CLAIMS.values() if topic in c.topics and c.kind in kinds]


def source_of(claim: Claim) -> EvidenceSource | None:
    return SOURCES.get(claim.source_id) if claim.source_id else None
