# Merge guide — Person 3 into the shared GitHub repo

## What this folder is

`person3-grok/` is the Person 3 tree (Grok, vision v2, presence trigger, bridge). It lives beside `dog backend/` and `ground base/`. Nothing in those two directories is edited by this change.

Origin `https://cursor.com/codebase/hritvik-arora/robot-patrol` at `main` merge `1f5b6c69246f4a7c4bb2acf7482f6febe9026479` was the source of truth. This checkout had no Origin session (`CURSOR_AUTH_TOKEN` was not injected), so the tree was reconstructed from the Person 3 handoff plus Linear HAC-62 and HAC-58, and checked against Ground's published schema. It is not a byte copy of the 484-test Origin tree. Do not treat a green pytest here as that Origin count.

## How to import it

```bash
export PYTHONPATH="/absolute/path/to/grok-hackathon-pavia/person3-grok"
export PATROL_TEAM_REPO="/absolute/path/to/grok-hackathon-pavia"
```

`PATROL_TEAM_REPO` may instead be the `ground base` directory.

Leave `ground base` and `dog backend` off `PYTHONPATH`. Both already contain a `patrol` package with `patrol/__init__.py`. Putting them on the path next to this folder hides either `patrol.grok` or `patrol.ground`.

The bridge loads Ground with `importlib` from `PATROL_TEAM_REPO`. That is the supported way to run presence and the bridge against Ayush's checkers in one process.

| Need | Where |
| --- | --- |
| Our imports (`patrol.grok`, `patrol.vision_v2`, `patrol.trigger`, `patrol.bridge`) | `PYTHONPATH=person3-grok` |
| Ground schema, g16, g17 | `PATROL_TEAM_REPO` (repo root or `ground base`) |
| Dog runtime | `dog backend/` on its own `PYTHONPATH`, in a separate process. Not used by these tests. |

## What not to merge into Ground or the dog

Do not patch `ground base/` or `dog backend/` from this folder to accept `play_warning`, `follow`, `stop` (as `dog.command`), `return_home`, or `land_on_dog`. That is HAC-58, owned by Ayush (schema and factories), Leo (dog runtime), and the drone owner (`land_on_dog`).

`python -m patrol.vision_v2` exits 2 until Ground publishes `/ws/robot/v2` host, port, and auth. Do not fill those in.

## Checks before merging this folder

```bash
cd person3-grok
PYTHONPATH="$PWD" python3 -m pytest
PYTHONPATH="$PWD" python3 -m patrol.bridge.probe
```

The probe rewrites `handoff/ground_rejection_log.md`. Commit that file with the code so the rejection record stays next to the emitters.
