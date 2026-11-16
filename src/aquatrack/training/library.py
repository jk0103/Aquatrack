"""The curated activity library and the sources behind it.

Small on purpose. An activity is used in a plan only if it is `active`, and it is described
as supported by research or by coaching guidance only where a source below was actually
checked. Research sources: DOI looked up at Crossref, abstract read at PubMed (abstracts
only, never full texts). Coaching pages: the page was fetched and read on the date recorded.
Durations, repeats, rest and the order of a session are AquaTrack's own conservative
choices unless a line says otherwise. No source here shows that any activity improves a
particular swimmer's technique or times.
"""
# ruff: noqa: E501  (instructions and limits are kept whole, one per line)

from aquatrack.training.models import Activity, TrainingSource

LIBRARY_VERSION = "2026.11-1"
VERIFIED_ON = "2026-11-16"

_RESEARCH = "Crossref record by DOI; abstract read at PubMed (abstract only)"
_PAGE = "Page fetched and read (automated fetch) on the date recorded"

SOURCES: dict[str, TrainingSource] = {
    s.id: s
    for s in [
        TrainingSource(
            id="neiva2014",
            kind="review",
            title="Warm-Up and Performance in Competitive Swimming",
            authors=["Neiva HP", "Marques MC", "Barbosa TM", "Izquierdo M", "Marinho DA"],
            year=2014,
            publisher="Sports Medicine 44:319-330",
            doi="10.1007/s40279-013-0117-y",
            url="https://doi.org/10.1007/s40279-013-0117-y",
            verified_on=VERIFIED_ON,
            verified_via=_RESEARCH,
            read="abstract",
            says="A review of warm-up in competitive swimming: studies are few and do not all agree, but recent findings point to a positive effect on performance, especially over distances longer than 200 m.",
            limits="About competitive swimmers before racing. Its recommended warm-up (1,000 to 1,500 m) is for that setting and is not used here; AquaTrack's warm-up length is its own conservative choice.",
        ),
        TrainingSource(
            id="mcgowan2015",
            kind="review",
            title="Warm-Up Strategies for Sport and Exercise: Mechanisms and Applications",
            authors=["McGowan CJ", "Pyne DB", "Thompson KG", "Rattray B"],
            year=2015,
            publisher="Sports Medicine 45:1523-1546",
            doi="10.1007/s40279-015-0376-x",
            url="https://doi.org/10.1007/s40279-015-0376-x",
            verified_on=VERIFIED_ON,
            verified_via=_RESEARCH,
            read="abstract",
            says="A review across sports: an active warm-up changes temperature, metabolism and readiness for the exercise that follows; the review notes that warm-up practice has largely grown from experience and that evidence was modest until recently.",
            limits="General sport and pre-competition focus, not recreational swimming practice.",
        ),
        TrainingSource(
            id="vanhooren2018",
            kind="review",
            title="Do We Need a Cool-Down After Exercise? A Narrative Review of the Psychophysiological Effects and the Effects on Performance, Injuries and the Long-Term Adaptive Response",
            authors=["Van Hooren B", "Peake JM"],
            year=2018,
            publisher="Sports Medicine 48:1575-1595",
            doi="10.1007/s40279-018-0916-2",
            url="https://doi.org/10.1007/s40279-018-0916-2",
            verified_on=VERIFIED_ON,
            verified_via=_RESEARCH,
            read="abstract",
            says="A narrative review: an active cool-down is largely ineffective for most markers of recovery after exercise, though it may offer some benefits compared with doing nothing.",
            limits="This is why the cool-down here is described only as an easy way to end a session, not as something with a shown benefit.",
        ),
        TrainingSource(
            id="mcgibbon2018",
            kind="review",
            title="Pacing in Swimming: A Systematic Review",
            authors=["McGibbon KE", "Pyne DB", "Shephard ME", "Thompson KG"],
            year=2018,
            publisher="Sports Medicine 48:1621-1633",
            doi="10.1007/s40279-018-0901-9",
            url="https://doi.org/10.1007/s40279-018-0901-9",
            verified_on=VERIFIED_ON,
            verified_via=_RESEARCH,
            read="abstract",
            says="A systematic review of pacing in competitive swimming races: holding speed matters in short and middle distances, and low lap-to-lap variability in long ones.",
            limits="About race pacing in competitive swimmers. It does not test practice sets, and it says nothing about AquaTrack's rhythm measurement.",
        ),
        TrainingSource(
            id="swimengland_frontcrawl",
            kind="coaching_page",
            title="Improving your front crawl technique",
            year=2018,
            publisher="Swim England (Masters Swimming Hub, swimming.org)",
            url="https://www.swimming.org/masters/improving-front-crawl-technique/",
            verified_on=VERIFIED_ON,
            verified_via=_PAGE,
            read="page",
            says="General front crawl guidance: a flat, streamlined body; head in line with the body, looking forward and slightly down and kept still except to breathe; a steady, continuous kick with small movements.",
            limits="General coaching guidance for adult swimmers, not a study, and not about any one swimmer.",
        ),
        TrainingSource(
            id="swimengland_breathing",
            kind="coaching_page",
            title="Front crawl breathing drills",
            year=2018,
            publisher="Swim England (Masters Swimming Hub, swimming.org)",
            url="https://www.swimming.org/masters/front-crawl-breathing-drills/",
            verified_on=VERIFIED_ON,
            verified_via=_PAGE,
            read="page",
            says="Breathing practice in steps: kicking with a kickboard while breathing out steadily into the water and turning the head to breathe in, then full stroke breathing every three strokes.",
            limits="The page's first step (staying under while breathing out for longer and longer) is deliberately not used here. General coaching guidance, not a study.",
        ),
        TrainingSource(
            id="usms_kick",
            kind="coaching_page",
            title="Freestyle Kick: Flutter Kick the Right Way",
            authors=["Sheaff A"],
            publisher="U.S. Masters Swimming (usms.org)",
            url="https://www.usms.org/fitness-and-training/guides/freestyle/kick",
            verified_on=VERIFIED_ON,
            verified_via=_PAGE,
            read="page",
            says="A coaching guide to the freestyle kick: kicking on your side moves you forward as freestyle does and also works on body position and alignment.",
            limits="General coaching guidance for adult swimmers, not a study.",
        ),
        TrainingSource(
            id="usms_30min",
            kind="coaching_page",
            title="The 5 Best 30-minute Swim Workouts",
            authors=["Topper H"],
            year=2026,
            publisher="U.S. Masters Swimming (usms.org)",
            url="https://www.usms.org/fitness-and-training/articles-and-videos/articles/the-5-best-30-minute-swim-workouts",
            verified_on=VERIFIED_ON,
            verified_via=_PAGE,
            read="page",
            says="Short workouts by a masters coach, each built as warm-up, drill set, main set and cool-down, with catch-up among the drills; it says many adult swimmers cover roughly 1,000 to 1,500 yards in 30 minutes and stresses technique and controlled effort.",
            limits="Used only for the shape of a session and as an upper reference for distance; AquaTrack's own distance guides are set lower. Not a study.",
        ),
    ]
}

# Checked and left out: see docs/TRAINING.md. Nothing below cites them.

_STOP = "Stop and rest if you feel dizzy, unusually short of breath or unwell."
_BREATHE = (
    "Breathe whenever you need to. Never hold your breath or limit your breathing on purpose."
)
_OWN_PACE = "The repeats and rest are a guide. Do fewer, or rest longer, whenever you want to."
_NO_PROOF = "No source in the library shows that this activity changes a particular swimmer's technique or times."
_ALL = ["beginner", "hobby", "masters", "competitive"]
_NOT_BEGINNER = ["hobby", "masters", "competitive"]


def _a(**kw) -> Activity:
    kw.setdefault("safety", [_STOP, _BREATHE])
    kw.setdefault("limitations", [_NO_PROOF, _OWN_PACE])
    return Activity(**kw)


ACTIVITIES: dict[str, Activity] = {
    a.id: a
    for a in [
        _a(
            id="warm.easy_swim",
            name="Easy warm-up swim",
            category="warm_up",
            stroke="Any",
            levels=_ALL,
            purpose="Start gently before the rest of the session.",
            instructions=[
                "Swim easily, in any stroke you like, at a pace where you could talk afterwards.",
                "Take a short rest at the wall whenever you want one.",
            ],
            min_minutes=5,
            max_minutes=15,
            repeat_m=50,
            intensity="easy",
            rest="About 15 to 30 seconds at the wall between repeats, longer if you want.",
            evidence_class="research_supported",
            source_ids=["neiva2014", "mcgowan2015", "usms_30min"],
            limitations=[
                "Reviews describe warming up as widely accepted, with mixed evidence in swimming; they studied competitive swimmers before races.",
                "How long this warm-up lasts is AquaTrack's own conservative choice, not a value from those reviews.",
                _OWN_PACE,
            ],
        ),
        _a(
            id="tech.count_strokes",
            name="Count your strokes",
            category="rhythm_awareness",
            levels=_ALL,
            purpose="Notice your own stroke rhythm from one length to the next.",
            instructions=[
                "Swim one length of easy freestyle and count every hand entry.",
                "Rest, then swim the next length at the same easy effort and count again.",
                "Just notice whether the count stays the same. There is no number to aim for.",
            ],
            min_minutes=5,
            max_minutes=10,
            repeat_m=25,
            intensity="easy",
            rest="About 20 to 30 seconds between lengths.",
            goals=["stroke_consistency", "overall_freestyle", "arm_technique", "speed"],
            metric_keys=["rhythm_variation", "cycle_duration"],
            rule_ids=["timing.uneven_rhythm", "history.rhythm_less_steady"],
            watch_for="Whether your count per length stays the same when the effort stays the same.",
            video_can_measure="A later side-view clip of six or more stroke cycles lets AquaTrack measure how much your cycle time varies.",
            evidence_class="general_suggestion",
        ),
        _a(
            id="tech.even_pace",
            name="Even-effort repeats",
            category="rhythm_awareness",
            levels=_ALL,
            purpose="Practise swimming repeats at one steady, comfortable effort.",
            instructions=[
                "Swim each repeat of freestyle at the same comfortable effort, not fast.",
                "Try to make the last repeat feel the same as the first.",
                "If the effort starts to climb, rest longer before the next one.",
            ],
            min_minutes=5,
            max_minutes=15,
            repeat_m=50,
            intensity="moderate",
            rest="About 20 to 30 seconds between repeats.",
            goals=["stroke_consistency", "speed", "endurance"],
            metric_keys=["rhythm_variation", "stroke_rate"],
            rule_ids=["timing.uneven_rhythm", "history.rhythm_less_steady"],
            watch_for="Whether the effort and your stroke count feel the same from the first repeat to the last.",
            video_can_measure="A later clip filmed the same way lets AquaTrack compare your stroke rate and how much your cycle time varies.",
            evidence_class="general_suggestion",
            source_ids=["mcgibbon2018"],
            limitations=[
                "A review found that even pacing matters in competitive races; it did not test practice repeats like these.",
                _NO_PROOF,
                _OWN_PACE,
            ],
        ),
        _a(
            id="tech.head_still",
            name="Still head, eyes down",
            category="body_position",
            levels=_ALL,
            purpose="Practise a steady head position while swimming easy freestyle.",
            instructions=[
                "Swim easy freestyle looking down and slightly forward.",
                "Keep your head still between breaths and turn it only to breathe.",
                "Keep the kick small and steady.",
            ],
            min_minutes=5,
            max_minutes=10,
            repeat_m=25,
            intensity="easy",
            rest="About 20 to 30 seconds between lengths.",
            goals=["body_alignment", "overall_freestyle"],
            metric_keys=["head_height", "body_line_angle"],
            watch_for="Whether your head stays quiet between breaths.",
            video_can_measure="A steady underwater side-view clip lets AquaTrack measure your head position and body line.",
            evidence_class="coaching_guidance",
            source_ids=["swimengland_frontcrawl"],
        ),
        _a(
            id="tech.side_kick",
            name="Kick on your side",
            category="body_position",
            levels=_ALL,
            purpose="Practise holding a long, level body while kicking.",
            instructions=[
                "Push off gently at the surface and kick on your side with the lower arm stretched in front.",
                "Keep your face in the water looking down; turn your head to breathe as often as you like.",
                "Change sides each length.",
            ],
            min_minutes=5,
            max_minutes=10,
            repeat_m=25,
            intensity="easy",
            rest="About 30 seconds between lengths.",
            goals=["body_alignment", "overall_freestyle"],
            metric_keys=["body_line_angle", "leg_line_angle"],
            watch_for="Whether your hips and legs stay near the surface.",
            video_can_measure="A steady underwater side-view clip of normal freestyle lets AquaTrack measure your body and leg line. It does not measure the drill itself.",
            evidence_class="coaching_guidance",
            source_ids=["usms_kick"],
        ),
        _a(
            id="tech.kickboard_breathing",
            name="Kickboard breathing",
            category="breathing",
            levels=_ALL,
            purpose="Practise breathing out into the water and turning to breathe in.",
            instructions=[
                "Hold a kickboard in front and kick gently with your face in the water.",
                "Breathe out steadily into the water, then turn your head to the side to breathe in.",
                "Breathe as often as you need to. This is not a breath-control exercise.",
            ],
            min_minutes=5,
            max_minutes=10,
            repeat_m=25,
            intensity="easy",
            rest="About 30 seconds between lengths.",
            equipment=["kickboard"],
            goals=["breathing"],
            watch_for="Whether breathing out in the water feels relaxed.",
            video_can_measure="AquaTrack does not measure breathing.",
            evidence_class="coaching_guidance",
            source_ids=["swimengland_breathing"],
        ),
        _a(
            id="tech.breathe_every_three",
            name="Regular breathing rhythm",
            category="breathing",
            levels=_ALL,
            purpose="Practise a regular breathing pattern in easy freestyle.",
            instructions=[
                "Swim easy freestyle and breathe out steadily while your face is in the water.",
                "Try breathing every three strokes if that is comfortable; breathe every two whenever you prefer.",
                "Never stretch the gap between breaths.",
            ],
            min_minutes=5,
            max_minutes=10,
            repeat_m=25,
            intensity="easy",
            rest="About 20 to 30 seconds between lengths.",
            goals=["breathing", "endurance"],
            watch_for="Whether your breathing stays relaxed for the whole length.",
            video_can_measure="AquaTrack does not measure breathing.",
            evidence_class="coaching_guidance",
            source_ids=["swimengland_breathing"],
        ),
        _a(
            id="tech.catch_up",
            name="Catch-up freestyle",
            category="arm_coordination",
            levels=_ALL,
            purpose="Practise the timing of one arm stroke after the other.",
            instructions=[
                "Swim easy freestyle, leaving one arm stretched in front until the other hand comes forward to meet it.",
                "Keep kicking gently and breathe as usual.",
                "Swim it slowly. It is a coordination exercise, not a way to swim.",
            ],
            min_minutes=5,
            max_minutes=10,
            repeat_m=25,
            intensity="easy",
            rest="About 20 to 30 seconds between lengths.",
            goals=["arm_technique"],
            watch_for="Whether each arm finishes its stroke before the next one starts.",
            video_can_measure="AquaTrack shows arm measurements for information only and does not judge the pull.",
            evidence_class="general_suggestion",
            source_ids=["usms_30min"],
            limitations=[
                "Named as a common drill in a coaching article; the article does not describe what it achieves.",
                _NO_PROOF,
                _OWN_PACE,
            ],
        ),
        _a(
            id="main.easy_repeats",
            name="Easy freestyle repeats",
            category="basic_freestyle",
            levels=_ALL,
            purpose="Unhurried freestyle practice with plenty of rest.",
            instructions=[
                "Swim each repeat of freestyle at an easy effort.",
                "Rest at the wall until your breathing has settled before the next one.",
            ],
            min_minutes=5,
            max_minutes=60,
            repeat_m=50,
            intensity="easy",
            rest="About 30 seconds between repeats, longer if you want.",
            goals=["overall_freestyle", "stroke_consistency", "body_alignment", "breathing"],
            evidence_class="general_suggestion",
        ),
        _a(
            id="main.technique_swim",
            name="Easy swim with one focus",
            category="basic_freestyle",
            levels=_ALL,
            purpose="Carry one point from the technique practice into normal swimming.",
            instructions=[
                "Swim easy freestyle repeats.",
                "On each repeat keep one thing in mind from the practice you did just before.",
                "Rest between repeats and start the next one unhurried.",
            ],
            min_minutes=5,
            max_minutes=60,
            repeat_m=50,
            intensity="easy",
            rest="About 30 seconds between repeats.",
            goals=[
                "overall_freestyle",
                "stroke_consistency",
                "body_alignment",
                "arm_technique",
                "breathing",
            ],
            evidence_class="general_suggestion",
        ),
        _a(
            id="main.steady_repeats",
            name="Steady freestyle repeats",
            category="endurance",
            levels=_NOT_BEGINNER,
            purpose="A moderate, steady block of swimming.",
            instructions=[
                "Swim each repeat at a steady effort you could hold for the whole set.",
                "Keep the effort the same from the first repeat to the last.",
                "Shorten the set if your stroke starts to feel rushed.",
            ],
            min_minutes=5,
            max_minutes=50,
            repeat_m=100,
            intensity="moderate",
            rest="About 20 to 30 seconds between repeats.",
            goals=["endurance", "speed", "stroke_consistency", "overall_freestyle"],
            evidence_class="general_suggestion",
        ),
        _a(
            id="main.pace_change",
            name="Easy and brisk 50s",
            category="endurance",
            levels=["masters", "competitive"],
            purpose="Practise changing pace under control.",
            instructions=[
                "Alternate one easy 50 with one brisk 50.",
                "Brisk means clearly faster than easy but controlled; never all-out.",
                "If your stroke falls apart, go back to easy repeats for the rest of the set.",
            ],
            min_minutes=10,
            max_minutes=30,
            repeat_m=50,
            intensity="brisk",
            rest="About 30 to 45 seconds between repeats.",
            goals=["speed"],
            evidence_class="general_suggestion",
            safety=[_STOP, _BREATHE, "Do this only after a warm-up, and not on two days in a row."],
        ),
        _a(
            id="cool.easy_swim",
            name="Easy cool-down swim",
            category="cool_down",
            stroke="Any",
            levels=_ALL,
            purpose="An easy way to finish the session.",
            instructions=[
                "Swim very easily, in any stroke you like, and stop when you feel settled."
            ],
            min_minutes=3,
            max_minutes=10,
            repeat_m=50,
            intensity="easy",
            rest="As much as you like.",
            evidence_class="general_suggestion",
            source_ids=["vanhooren2018"],
            limitations=[
                "A review found active cool-downs largely ineffective for most markers of recovery. It is included as a calm end to the session, not for a shown benefit.",
                _OWN_PACE,
            ],
        ),
        _a(
            id="tech.fingertip_drag",
            name="Fingertip drag",
            category="arm_coordination",
            levels=_ALL,
            purpose="Not used: no source describing it was checked.",
            instructions=["Not available."],
            min_minutes=5,
            max_minutes=10,
            intensity="easy",
            goals=["arm_technique"],
            evidence_class="unverified",
            active=False,
            limitations=["Kept out of plans until a source describing it has been read."],
        ),
    ]
}

CATEGORY_LABELS = {
    "warm_up": "Warm-up",
    "basic_freestyle": "Basic freestyle practice",
    "rhythm_awareness": "Stroke rhythm awareness",
    "body_position": "Body position awareness",
    "arm_coordination": "Arm movement coordination",
    "breathing": "Breathing practice",
    "endurance": "Moderate endurance swimming",
    "recovery": "Easy recovery swimming",
    "cool_down": "Cool-down",
    "video_checkpoint": "Video checkpoint",
    "custom": "Added by you",
}

# Words that would mean an exercise or piece of kit. A reworded plan may only use the ones
# that already appear in that plan's own text (see training/explain.py).
EXERCISE_TERMS = [
    "catch-up", "catch up", "fingertip", "sculling", "scull", "kickboard", "pull buoy", "fins",
    "paddles", "snorkel", "sprint", "all-out", "max effort", "dolphin", "underwater", "dive",
    "butterfly", "backstroke", "breaststroke", "tumble turn", "flip turn", "side kick",
    "kick on your side", "single-arm", "one-arm", "fist", "zipper", "vertical kick", "dryland",
    "weights", "stretching", "plank", "interval", "threshold", "race pace", "time trial",
]  # fmt: skip


def active() -> list[Activity]:
    return [a for a in ACTIVITIES.values() if a.active]


def eligible(activity: Activity, level: str | None, equipment: list[str]) -> str | None:
    """None if the swimmer can be offered this activity, otherwise the reason not."""
    if not activity.active:
        return "This activity is not available."
    if (level or "beginner") not in activity.levels:
        return f"{activity.name} is not offered at your swimming level."
    lacking = [e for e in activity.equipment if e not in equipment]
    if lacking:
        return f"{activity.name} needs a {lacking[0].replace('_', ' ')}, which is not in your equipment list."
    return None
