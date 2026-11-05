<!-- title: [Ground] patrol package name collision hides dog, grok, or ground -->

# [Ground] patrol package name collision hides dog, grok, or ground

## What we tried

        `MERGE_GUIDE` says not to put `ground base` or `dog backend` on `PYTHONPATH` next to `person3-grok`. We did it anyway, in both orders, and recorded which `patrol` was imported. We also imported `patrol.dog` with `PYTHONPATH` set to `dog backend` alone.

        ## Code path

        `person3-grok/patrol/__init__.py` and `ground base/patrol/__init__.py` are both regular packages.
`dog backend/patrol` has no `__init__.py` (`contract.py` and `patrol/dog/` only), so it is a namespace package. `patrol.__file__` is null when that tree is used alone, and `create_dog` still imports.
A regular package later on `sys.path` replaces the namespace. `PYTHONPATH="dog backend:person3-grok"` still loaded `person3-grok/patrol/__init__.py`, and `import patrol.dog` then failed.

        ## Error

        `person3` then `ground`: `patrol` is person3; `import patrol.ground` → `ModuleNotFoundError: No module named 'patrol.ground'`.
`ground` then `person3`: `patrol` is ground; `import patrol.grok` and `import patrol.bridge` fail.
`person3` then `dog`, and `dog` then `person3`: `patrol` is person3; `import patrol.dog` fails.
Dog alone: `create_dog(*, mode, config, output_dir)` succeeded in fake mode. `has_execute` false, `has_play_warning` false.

        ## Why this blocks the demo

        One process cannot see Ground's checkers and Vik's reasoner and Leo's dog through normal imports. g08's `importlib.import_module("patrol.grok")` will bind whichever `patrol` is first and then miss the other components. The bridge avoids this only for g11/g16/g17 by loading files directly.

        ## Suggested fix owner

        Ayush, Leo, and Vik. The three trees need distinct top-level packages, or one namespace package with no `__init__.py` in any of them. Until then, do not concatenate these directories on `PYTHONPATH`.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
