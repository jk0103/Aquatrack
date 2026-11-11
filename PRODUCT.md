# Product

<!-- impeccable:product-schema 1 -->

<!-- Written by `/impeccable init` on 2026-11-03. The interview answers came from the owner's brief
relayed through the Aquatrack project rather than a live question round; anything marked
(inferred) comes from the repository and still needs the owner's confirmation. -->

## Platform

web

## Users

Swimmers of every level: beginners, hobby swimmers, masters swimmers and competitive swimmers.
They film themselves (or are filmed) underwater from the side or from overhead, upload the clip,
and want to understand what to change in their technique to swim faster and more efficiently.
The swimmer's level is captured at onboarding and shapes how feedback is pitched.

## Product Purpose

Aquatrack turns a swim video into personalized technique feedback. It tracks the swimmer's body
with pose estimation, measures stroke mechanics (stroke rate, left-right balance, rotation, kick
rhythm), and interprets those numbers alongside the swimmer's goals, records and video history.
Success is a swimmer who knows what to work on next and can see it improve over time.

## Positioning

Feedback is measured from the swimmer's own footage and read against their own history and
goals, instead of generic drills or a coach's one-off eye. (inferred from README)

## Operating Context

- Main flow: upload a clip on Analyze, read the result on Feedback, follow up in Training and
  Calendar, and track change in Progress and History. Profile and onboarding hold level, goals
  and records.
- Clips are underwater side view or overhead; tracking quality depends on the camera angle.
- Used on laptops and on phones (often near the pool).

## Capabilities and Constraints

- Frontend: Next.js (App Router) + Tailwind in `frontend/`. Backend: FastAPI + Python analysis in
  `src/aquatrack/`. Accounts, profiles and videos in Firebase (Auth, Firestore, Storage).
- Metrics built so far: stroke rate and arm symmetry; rotation and kick rhythm are planned.
  Written feedback is planned via the Claude API. (inferred from README and code)
- Metric units only (metres, seconds, etc.). No imperial units anywhere.
- Light and dark mode are both required.
- Navigation: a sidebar on laptop widths; on small screens a full-height side panel.

## Brand Commitments

Binding constraints the owner has stated (recorded, not expanded):

- Subtle frosted glass over a soft water background, on every page.
- Pool-blue accents.
- No large empty open space; layouts should feel filled and purposeful.
- No segmented or striped progress bars; progress uses smooth, animated fills.

## Evidence on Hand

- Home hero photo of a butterfly swimmer: `frontend/public/images/hero-butterfly.jpg`.
- No real user results, testimonials or benchmarks exist yet. Sample numbers in the UI (monthly
  gains, time drops, session counts, training plans, example feedback) are placeholders and must
  read as examples, never as the user's real data.

## Product Principles

1. Every insight traces back to something measured in the swimmer's own video.
2. Pitch feedback to the swimmer's level: plain and encouraging for beginners, precise for
   competitive swimmers.
3. Show progress over time, not just a single score.
4. Be honest about what is measured, estimated or still an example.
