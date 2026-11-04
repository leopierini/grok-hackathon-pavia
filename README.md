# Grok Hackathon at the Museum, Pavia

- [`dog backend/`](dog%20backend/README.md) is the Go2 dog code: adapters, joystick, LiDAR, safety, and the dog tests.
- [`ground base/`](ground%20base/README.md) is the Ground station. Tasks 11–32 are integrated there.

Pull requests run three Ground checks:

- Pytest
- Task simulations (32 tasks × seeds 0, 7, and 29)
- Composed demos (10 scenarios × Ethernet/Wi-Fi × the same three seeds)
