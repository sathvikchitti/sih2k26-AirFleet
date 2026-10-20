---
title: Air Fleet API
emoji: ✈️
colorFrom: gray
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Air Fleet Readiness API

FastAPI backend for the Aircraft Fleet Readiness & Sustainment Platform (SIH 2026, PS 26249, Team Teen Titans).

Every route except `/livez` requires HTTP Basic credentials configured in the Space secret `DEMO_BASIC_USERS`.
The frontend is hosted separately on Vercel and forwards `/api/*` and `/login` to this Space.

Data: NASA C-MAPSS FD001 (simulated turbofan engines). This is a proof of concept, not a certified maintenance system.
