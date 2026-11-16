"""The restricted demonstration's pose source: saved pose data for the approved test video.

Nothing here runs a model or invents a result. The uploaded file's SHA-256 selects the pose
file (kept in the demonstration project's own bucket, backend-only), the usual checks compare
it with the video, and the normal analysis, interpretation and feedback run on it. Any other
video fails with a plain explanation.
"""

from aquatrack.analysis.pose.sources import (
    DEMO_UNSUPPORTED,
    PoseSource,
    PrecomputedPoseSource,
    pose_source_from_env,
)
from aquatrack.api import config
from aquatrack.contracts import ModelConfig

# Where the demonstration's pose files live in the project's bucket. No storage rule
# matches this prefix, so no client can read or write it.
FIXTURE_PREFIX = "demo_fixtures/pose/"


def configure(source: PoseSource, store) -> PoseSource:
    """In demo mode, let a precomputed source fetch its file from the bucket and say why
    another video cannot be analysed. Outside demo mode the source is returned unchanged."""
    if config.demo_mode() and isinstance(source, PrecomputedPoseSource):
        source.fetch = getattr(store, "fetch_pose_fixture", None)
        source.missing_message = DEMO_UNSUPPORTED
        source.missing_retryable = False
    return source


def build_pose_source(store, model_config: ModelConfig | None = None) -> PoseSource:
    """The pose source for this process. Refuses saved pose data in a real project unless
    this is the restricted demonstration, so the fixture can never serve an open or a
    production deployment by a left-over setting."""
    problem = config.fixture_problem()
    if problem:
        raise RuntimeError(problem)
    return configure(pose_source_from_env(model_config), store)
