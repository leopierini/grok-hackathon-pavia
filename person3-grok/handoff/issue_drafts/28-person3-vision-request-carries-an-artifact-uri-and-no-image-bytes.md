<!-- title: [Person3] vision.request carries an artifact URI and no image bytes -->

# [Person3] vision.request carries an artifact URI and no image bytes

## What we tried

        We built the `vision.request` for `dog_approach` and `drone_track` with `build_request` and validated both with g11. Both were accepted. We then looked for the JPEG the request names.

        ## Code path

        `person3-grok/patrol/vision_v2/decision.py` `build_request` sets `image_ref` to `artifact://{mission}/{stage}/{frame}.jpg` and a fixed sha256. `camera_id` is `front` or `downward`. No file is opened and no bytes are attached.
A repo search found no `dog-front-presence-001` image. `contracts/README.md` in Ground says `artifact://` is not an xAI image URL and vision must resolve it.

        ## Error

        Schema accepted the request. There is no local image behind the URI, so a reasoner cannot be given frame bytes. This did not raise; the gap shows up when you try to answer the request.

        ## Why this blocks the demo

        The request shape is legal and still not answerable. Combined with the missing API key, the presence loop cannot ask Grok whether the person is still there.

        ## Suggested fix owner

        Vik for resolving the artifact to bytes before a model call. Ayush if Ground must publish the artifact store the `image_ref` points at.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
