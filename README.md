# Grok Hackathon at the Museum: Pavia, 4–5 Nov 2026

Our team's workspace for the [Grok Hackathon](https://pavia.grokbot.it/) at Ctrl+Alt Museum.

- **[project-plan.md](./project-plan.md)**: ⭐ **current plan**: concept, demo flow, architecture, metrics, team split
- **[docs/dog.md](./docs/dog.md)**: 🐕 dog (Go2) working notes: how to connect, known facts, tasks, session log
- **[reports/Robot dog and drone patrol.md](./reports/Robot%20dog%20and%20drone%20patrol.md)**: research report (prior art, feasibility, Track D strategy); sources in `research_notes/`
- **[hackathon info.md](./hackathon%20info.md)**: everything about the event (tracks, rules, schedule, jury, hardware, kickoff slides)
- **[robot-docs/](./robot-docs/README.md)**: SDK index for the Unitree Go1/Go2 dogs, the Tello EDU drone and the cobots. Run `./robot-docs/fetch-sdks.sh` to download the SDKs
- **[slides/](./slides/Grok-Hackathon-kickoff.pdf)**: kickoff slides (PDF + extracted text)
- **scraped/**: raw text dumps of the website

**Current focus: Track D, Robot Dog Patrol (Riello).** *Grok, the night-shift operator that asks before it alarms.* Phone cameras detect an event, Grok sends the **Go2**, and when the dog's view is blocked Grok launches the **Tello EDU from the dog's back** for a look from above. The dog can talk to the person it finds, Grok checks plain-language site rules, and the caretaker gets an Italian voice alert. See [project-plan.md](./project-plan.md).

Backup ideas: Agent Failure Lab, LabOS.

⏰ **Thursday 16:00:** ~2-min video demo + minimum demo on a jury case. Pitches 16:00–19:00.
