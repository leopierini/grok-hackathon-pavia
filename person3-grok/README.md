# Person 3 — Grok, presence, bridge

This folder is Vik's side of the shared hackathon repo. It does not replace `dog backend/` or `ground base/`. Do not add this tree's `patrol` package and Ground's `patrol` package to `PYTHONPATH` at the same time: Python will import only the first `patrol` it finds.

Origin `hritvik-arora/robot-patrol` (`main` at `1f5b6c6`) was not readable from the machine that built this folder (no Origin session). The layout matches that tree. The code here is the presence path from HAC-62 reconstructed against Ayush's `2.0-draft` schema in `ground base/`:

- `patrol/grok` — fake reasoner factory `create_reasoner`, presence prompt `patrol-presence-v1`
- `patrol/vision_v2` — `vision.request` / `vision.decision` builder; `python -m patrol.vision_v2` exits 2
- `patrol/trigger` — post-dispatch presence session (warn, follow, stop, land, return, halt)
- `patrol/bridge` — proposals and command shapes, plus the Ground rejection probe
- `contracts/vision_v2` — pointer at Ground's schema (Ayush wins; no second copy)
- `config/grok.example.json` — model and latency knobs, no secrets
- `handoff/MERGE_GUIDE.md`, `handoff/grok_ground_integration.md`, `handoff/ground_rejection_log.md`

`patrol/contract.py` is the frozen v1.0 contract, copied unchanged.

## Paths

From the shared repo root:

```bash
export PYTHONPATH="$PWD/person3-grok"
# Point at the repo root, or directly at "ground base".
# Do not append "ground base" or "dog backend" to PYTHONPATH.
export PATROL_TEAM_REPO="$PWD"
```

`PATROL_TEAM_REPO` is how the bridge finds Ground (`ground base/patrol/ground/...`) and notes where `dog backend/` sits. The probe loads Ground by file path, so the two `patrol` packages do not collide.

Dog code is not imported. Its tests need the Unitree stack. The frozen contract in this folder is the copy the reasoner uses.

## Tests

```bash
cd person3-grok
python3 -m pytest
python3 -m patrol.bridge.probe
python3 -m patrol.vision_v2   # exits 2; host, port, and auth are unset
```

No API key is read. No host or port is invented.
