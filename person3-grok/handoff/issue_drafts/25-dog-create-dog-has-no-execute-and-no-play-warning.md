<!-- title: [Dog] create_dog has no execute and no play_warning -->

# [Dog] create_dog has no execute and no play_warning

## What we tried

        With `PYTHONPATH` set to `dog backend` only, we called `create_dog(mode="fake", config={}, output_dir=...)` and listed public methods. We did not connect to a robot. We compared them to `DogPort`.

        ## Code path

        `dog backend/patrol/dog/__init__.py` `create_dog` is keyword-only and returns `DogPort`.
`DogPort` methods: `connect`, `prepare`, `get_status`, `run_route`, `capture_frame`, `halt`, `close`.
`FakeDog` also has `say`, `play_audio_file`, `play_pcm`, `play_chime`, `stop_audio`, which are not on the port. There is no `execute`, no `play_warning`, and no handler for a v2 `dog.command`.

        ## Error

        `has_execute` false. `has_play_warning` false. `has_play_audio_file` true.
Signature: `(*, mode: Mode, config: Mapping[str, Any], output_dir: Path) -> DogPort`.
Ground g08 would call `run_route(zone)` for dog motion, not `execute(dog.command)`.

        ## Why this blocks the demo

        Even if Ayush accepted `play_warning`, `follow`, `stop`, or `return_home` on `dog.command`, this factory has nowhere to put them. `halt` exists. Speaking "go away" would require a new port method; `say` is not reachable through `DogPort`.

        ## Suggested fix owner

        Leo for the runtime. Ayush if v2 `execute(command)` is the port that should replace `run_route` for these actions.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
