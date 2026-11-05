# Grok Hackathon at the Museum, Pavia

- [`dog backend/`](dog%20backend/README.md) is the Go2 dog code: adapters, joystick, LiDAR, safety, and the dog tests.
- [`ground base/`](ground%20base/README.md) is the Ground station. Tasks 11–32 are integrated there.
- [`person3-grok/`](person3-grok/README.md) is Person 3 (Grok vision, presence trigger, and the Ground bridge). Set `PYTHONPATH` to that folder only. Point `PATROL_TEAM_REPO` at this repo root so the bridge can see `ground base` and `dog backend` without mixing `patrol` packages.

Pull requests run three Ground checks:

- Pytest
- Task simulations (32 tasks × seeds 0, 7, and 29)
- Composed demos (10 scenarios × Ethernet/Wi-Fi × the same three seeds)
