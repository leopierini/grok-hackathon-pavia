<!-- title: [Ground] /ws/robot/v2 host, port, and auth are unset -->

# [Ground] /ws/robot/v2 host, port, and auth are unset

## What we tried

        We ran `python -m patrol.vision_v2` from `person3-grok`. We checked the environment for robot and ground host, port, URL, and auth names. None were set. We did not invent a host or port and we did not open a socket. We also read Ground's contract note for the route.

        ## Code path

        `person3-grok/patrol/vision_v2/__main__.py` writes to stderr and returns 2.
`ground base/contracts/README.md` calls `/ws/robot/v2` a proposed route and says the host, port, and authentication are not configured. `ground base/docs/ground/scope-audit.md` says the route is not a deployed endpoint. `ground base/README.md` says an HTTP/WebSocket adapter is still to be added.
No listener is defined in this repo.

        ## Error

        Exit code 2.
stderr: `patrol.vision_v2: real mode exits 2; /ws/robot/v2 host, port, and auth are unset`.
Env names checked, all unset: `ROBOT_HOST`, `ROBOT_PORT`, `ROBOT_AUTH`, `ROBOT_WS_URL`, `GROUND_HOST`, `GROUND_PORT`, `GROUND_WS_HOST`, `GROUND_WS_PORT`, `GROUND_WS_URL`, `WS_ROBOT_HOST`, `WS_ROBOT_PORT`, `WS_ROBOT_AUTH`, `UNITREE_ROBOT_IP`.
Probe result: `attempted` false, reason `host, port, and auth are unset; no connection was opened`.
`dog.command` action `halt` does validate, and it still cannot be sent, because this transport is missing.

        ## Why this blocks the demo

        The post-dispatch loop cannot deliver a vision request, a decision, or a command to another process. Schema work would not move a robot until this route exists.

        ## Suggested fix owner

        Ayush to publish the real host, port, and auth for `/ws/robot/v2`. Vik must not fill those in. Leo if the dog app is the peer that must accept the route.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
