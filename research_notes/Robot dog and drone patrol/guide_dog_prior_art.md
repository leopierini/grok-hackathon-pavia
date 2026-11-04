# Robotic Guide Dogs and Guide Robots for Blind / Visually Impaired People: Prior Art (as of 4 Nov 2026)

## Q1. Which commercial or near-commercial robotic guide dogs or guide robots exist?

### Takeaway
As of November 2026 I found no quadruped guide dog that is sold to blind users. The nearest commercial product is Glidance Glide, a wheeled device with an AI agent that describes the scene, but its orders are closed and it runs a waitlist. Every quadruped guide dog I found (from SJTU, Binghamton, Glasgow, and Milo) is a research prototype or in field testing.

### Cited Findings
**Glidance Glide (USA, wheeled, near-commercial)**
- The company calls Glide "a new category of primary mobility aid." It has two all-terrain wheels, a telescoping handle, and it steers the user. Claimed features:
  - indoor and outdoor guidance
  - avoiding drop-offs, cracks, overhead branches and signs
  - finding doors, elevators and stairs
  - crosswalk help
  - tactile, haptic and audio cues
  - a "Glide Agent" that describes surroundings and guides the user to objects "within its line-of-sight"
  - over-the-air updates and a fleet-based AI model

  Source: [glidance.io](https://glidance.io)
- As of Nov 2026, orders are closed ("secure your spot on our waitlist for when we re-open orders"). The site shows no price. The images are renderings. The site has community profiles dated 5 Oct and 26 Oct 2026. — [glidance.io](https://glidance.io)
- 2024 pre-order material gave a retail price of $1,499 USD, with 40% off for founding members. It also listed a subscription of about $40/month and expected delivery in late 2025. — [AppleVis comment](https://applevis.com/comment/169229); [AppleVis comment](https://applevis.com/comment/169001)
- The device includes a speaker, microphones and Bluetooth audio. It was shown at CSUN 2025. — [Podfeet, CSUN 2025](https://www.podfeet.com/blog/2025/06/csun-2025-glidance/)

**SJTU six-legged robot guide dog (China, field testing, 2024)**
- Gao Feng's team at the Shanghai Jiao Tong University School of Mechanical Engineering built it on Lenovo's six-legged Daystar Bot GS.
- Users control it with voice commands and a tactile, telescopic force-feedback handlebar. It uses depth cameras and radar.
- The team cites about 400 guide dogs for about 20 million blind people in China.
- It was in field testing, and the team was working with Suochen Robot Co toward commercialization. No price was given.

  Sources: [SJTU news](https://global.sjtu.edu.cn/en/news/view/1775); [New Atlas](https://newatlas.com/robotics/six-legged-guide-robot-blind/); [heise](https://heise.de/-9796064); [VOA](https://learningenglish.voanews.com/amp/chinese-researchers-develop-robot-dogs-to-assist-the-blind/7681973.html)
- Later coverage (date not confirmed) says it can navigate autonomously, avoid obstacles dynamically and recognize traffic lights. — [Inspenet](https://inspenet.com/en/?p=169030)

**Milo (open-source autonomous robotic guide dog, research, Aug 2026)**
- The developers bill it as the "world's first fully autonomous robotic guide dog."
  - It navigates indoors and outdoors in unfamiliar places without a prior map or 3D scan, and builds a map as it moves.
  - It avoids obstacles and pedestrians and tracks the handler through sensors in a telescopic handle.
  - A D-pad sets speed and turn choices, and all AI runs onboard with no cloud.
  - The team projects it could be made for under $2,000.
  - Hardware designs, simulation software and models are open source.
  - It was trained with reinforcement learning in simulation and tested on obstacle courses. I found no reported study with blind users.
  - No LLM, VLM or voice features are mentioned.

  Sources: [Robotics & Automation News, 4 Aug 2026](https://roboticsandautomationnews.com/2026/08/04/researchers-unveil-open-source-robotic-guide-dog-designed-to-assist-blind-and-visually-impaired-people/103878/); [project page](https://fgolemo.github.io/milo/); [Open Source For You, Aug 2026](https://www.opensourceforu.com/2026/08/robotic-guide-dog-assists-independent-navigation/)

**.lumen glasses (Romania, wearable, not a robot)**
- They use AI, computer vision, LiDAR and IR, with haptic and voice guidance. The company says they detect stairs, doors, bus stops and puddles. — [New Atlas](https://newatlas.com/wearables/dotlumen-ai-glasses-blind-independence); [Interesting Engineering, CES 2025](https://interestingengineering.com/ces-2025/ai-powered-glasses-to-guide-the-blind)
- Listed price is about €9,999 incl. VAT; a 2025 interview gave €5–10k. A market launch was planned for early 2026, but I found no confirmed sales after CES 2026. — [EASTIN/REHADAT](https://www.eastin.eu/en/searches/products/detail/database-rehadat/id-tec_FD5DBFC4-B580-964C-956C-52F568E2849D); [dev.ua](https://dev.ua/en/news/rumunskyi-startap-lumen-zaproponuvav-okuliary-dlia-slipykh-tsinoiu-10-000-ievro-yak-pratsiuie-tekhnolohiia-1792408247); [AIN interview, Feb 2025](https://en.ain.ua/2025/02/20/interview-with-lumen); [The Gadgeteer, Dec 2025](https://the-gadgeteer.com/2025/12/26/what-happens-when-blind-navigation-stops-being-reactive/)

### Inferences
- The commercial bar is set by Glide: a wheeled device with an AI agent that describes scenes and finds objects. "AI that describes the scene and guides you to objects" is already a marketed feature, at least on a wheeled platform.
- No quadruped guide dog has reached retail. Quadruped work is still in research or field pilots, with open problems in safety, noise and cost.

### Gaps
- I could not verify these items in this session, so they are leads, not citable findings:
  - WeWalk smart cane (an AI cane; WeWalk 2 is reportedly LLM-enabled)
  - Biped NOA (a shoulder-worn harness with cameras)
  - Be My Eyes "Be My AI" (GPT-4 vision, 2023)
  - Toyota guide robots
  - KAIST guide robots
  - pilots by Guide Dogs or Lighthouse organisations
- The searches on KAIST and Toyota returned nothing relevant.
- I could not confirm Glide's current retail price or how many units have shipped as of Nov 2026.
- From memory and unverified here: the UC Berkeley Hybrid Robotics "Robotic Guide Dog: Leading a Human with Leash-Guided Hybrid Physical Interaction" on a Mini Cheetah (ICRA 2021). Verify the arXiv link before citing.

## Q2. Which research combines a quadruped guide robot with LLMs or VLMs for voice dialogue and scene description (2023–2026)?

### Takeaway
This combination has been published several times. The clearest overlap with the hackathon pitch is Binghamton's "From Woofs to Words" (AAAI 2026): a Unitree Go2 with GPT-4 that asks where the user wants to go and narrates the surroundings, tested with 7 legally blind users. Glasgow's RoboGuide (Go1 with an LLM, 2024) came earlier. Papers in 2026 add VLM fallback explanations, LLM explanations of navigation, coaching, and personalised object search.

### Cited Findings
**Binghamton University, "From Woofs to Words: Towards Intelligent Robotic Guide Dogs with Verbal Communication" (Shiqi Zhang lab, AAAI-26, Jan 2026; press Apr 2026)**
- Built on a Unitree Go2 with GPT-4. The robot asks the user's destination, plans a route and gives real-time commentary on the environment.
- Seven legally blind participants tested it in a multi-room indoor space under three conditions:
  - minimal voice interaction
  - environment descriptions only
  - full route planning plus commentary

  Participants preferred verbal plus physical guidance.

  Sources: [The Robot Report](https://www.therobotreport.com/binghamton-researchers-create-robotic-guide-dogs-that-walk-and-talk/); [TechXplore, Apr 2026](https://techxplore.com/news/2026-04-ai-powered-dogs-dont.html); [E&T, 9 Apr 2026](https://eandt.theiet.org/2026/04/09/talking-robot-dog-could-help-ease-shortage-guide-dogs-blind); [New Atlas](https://newatlas.com/robotics/robot-guide-dog/)
- Limitations:
  - One report says an expert monitored and remotely controlled the robot's physical movement, while voice, route selection and descriptions were automated.
  - Participants rated perceived safety slightly lower.
  - An expert noted that motor noise may interfere with echolocation.

  Sources: [Galaxus/Digitec](https://www.digitec.ch/en/page/guide-dog-20-this-robot-talks-and-guides-you-to-your-destination-42241); [TechXplore](https://techxplore.com/news/2026-04-ai-powered-dogs-dont.html)
- The reported figure of "77 navigation scenarios" conflicts between sources:
  - New Atlas says all 77 were completed.
  - Gadget Review cites 94.8% accuracy over 77 requests.
  - Another report says the 77 requests ran in a computer simulation.

  Sources: [New Atlas](https://newatlas.com/robotics/robot-guide-dog/); [Gadget Review](https://www.gadgetreview.com/?p=369001); [Let's Data Science](https://letsdatascience.com/news/binghamton-robot-dog-uses-gpt-4-to-guide-visually-impaired-6c913651)
- The team's stated next steps are more autonomy and longer indoor and outdoor trips. — [aboutaccess](https://aboutaccess.co.uk/robo-dogs-impress-in-trials/)

**RoboGuide, University of Glasgow (Unitree Go1 with an LLM, Feb 2024)**
- An indoor guide for museums and hospitals. It uses 3D environment scanning and LLM-based answers to user queries. It was trialled at the Hunterian Museum with RNIB Scotland and the Forth Valley Sensory Centre. The PI is Dr Olaoluwa Popoola.

  Sources: [The Engineer](https://theengineer.co.uk/content/news/roboguide-walks-and-talks-to-assist-blind-and-partially-sighted-people); [TNW, 13 Feb 2024](https://thenextweb.com/news/robot-guide-dog-for-blind-partially-sighted); [The Robot Report](https://www.therobotreport.com/?p=577925); [Verdict](https://www.verdict.co.uk/university-of-glasgows-robot-guide-dog-leads-the-way-in-assistive-technology/)

**Other papers**
- **"Lightweight and Resource-Efficient Perception for Robotic Guide Dogs"** (arXiv 2610.03187, Oct 2026, ACCV 2026)
  - Fuses a 360° camera with a 2D LiDAR on a quadruped, with moving-object tracking and descriptions of obstacles relative to the user.
  - A VLM explains the pathway only when walking is impossible.
  - Scores 83.8% on GuideDogQA vs 67.1% for GPT-4o, and runs in real time under 55 W.

  Source: [arXiv](https://arxiv.org/abs/2610.03187)
- **"Navigation Explainability for Object Avoidance with LLMs for Assistive Robots"** (arXiv 2610.28920, Oct 2026). An LLM turns the guide dog's obstacle-avoidance decisions and trajectory into natural-language explanations. The related LaF-GRPO work uses an LLM that simulates a blind user to post-train a VLM. — [arXiv](https://arxiv.org/abs/2610.28920); [ResearchGate listing](https://www.researchgate.net/publication/380523328_Navigating_Real-World_Challenges_A_Quadruped_Robot_Guiding_System_for_Visually_Impaired_People_in_Diverse_Environments)
- **RoboFind** (arXiv 2609.20330, Sep 2026, KIT group incl. Stiefelhagen and Asfour)
  - Multi-agent, personalised search for the user's own object on a quadruped. Agents handle target teaching via smartphone, navigation, verification, and coordination and recovery.
  - Achieves 85% success vs 25% for the baseline over real-robot missions, and false successes fall from 75% to 5%.
  - The page names a "GPT-6 Astra-only" baseline, reproduced as written.
  - No study with blind users is reported.

  Source: [arXiv](https://arxiv.org/abs/2609.20330)
- **CANINE** (arXiv 2605.19501, RSS 2026, David Hsu's group). Foundation models infer users' errors and give adaptive verbal coaching for training on a robot guide dog. Tested with blindfolded participants plus one visually impaired user. — [arXiv](https://arxiv.org/abs/2605.19501)
- **"Not an Obstacle for Dog, but a Hazard for Human: A Co-Ego Navigation System"** (arXiv 2603.20121, Mar 2026). It models the user's body-height exposure zone, because obstacles a dog can pass may still be hazards for a human. — [arXiv](https://arxiv.org/pdf/2603.20121)
- **GuideDog dataset** (arXiv 2503.12844, Mar 2025). A real-world egocentric multimodal dataset for accessibility-aware guidance, the basis of the GuideDogQA benchmark. — [arXiv](https://arxiv.org/pdf/2503.12844)
- **CognitiveDog** (HRI 2024 companion, Unitree Go1). A large multimodal model translates vision and language into talking and object manipulation. It is general purpose, not a guide dog. — [ACM DL](https://dl.acm.org/doi/10.1145/3610978.3641080)
- **Other titles seen but not read in detail:**
  - "GuideNav" (arXiv 2512.06147)
  - "Understanding Expectations for a Robotic Guide Dog for Visually Impaired People" (arXiv 2501.04594, Jan 2025)
  - "Human-Centered Development of Guide Dog Robots: Quiet and Stable Locomotion Control" (arXiv 2505.11808, 2025)
  - "Quadruped Guidance Robot for the Visually Impaired: A Comfort-Based Approach" (arXiv 2203.03927, 2022)

  Sources: [2501.04594](https://arxiv.org/pdf/2501.04594); [2505.11808](https://arxiv.org/pdf/2505.11808); [2203.03927](https://arxiv.org/pdf/2203.03927)

### Inferences
- "Quadruped guide dog + LLM voice dialogue + scene narration" is published prior art: Glasgow in 2024 on a Go1, and Binghamton at AAAI 2026 on a Go2 with GPT-4, the same base robot as the hackathon team. The team cannot credibly claim this core combination as new.
- Research has shifted toward finer sub-problems: when to talk (sparse or fallback VLM), explaining avoidance manoeuvres, user training and coaching, personalised object search, and human-height hazards.

### Gaps
- I did not read the full Binghamton paper. Its exact autonomy level, sensors (whether it uses LiDAR) and the real-world vs simulated split of the 77 requests are unconfirmed.
- The RoboFind and 2610.03187 abstracts do not name the quadruped model.

## Q3. Have the Unitree Go1 or Go2 been used as guide dogs?

### Takeaway
Yes, many times. The Go2 is the de facto research platform for this (Binghamton, ASU), and the Go1 has been used by Glasgow, CognitiveDog and open-source ROS 2 repos.

### Cited Findings
- Binghamton "From Woofs to Words" uses a Unitree Go2 with GPT-4. — [The Robot Report](https://www.therobotreport.com/binghamton-researchers-create-robotic-guide-dogs-that-walk-and-talk/)
- Glasgow RoboGuide uses a Unitree Go1. — [The Engineer](https://theengineer.co.uk/content/news/roboguide-walks-and-talks-to-assist-blind-and-partially-sighted-people)
- **GenAssist** (ASU FURI student project, 2026): a Unitree Go2 with an RGB-D camera, YOLOv8 and a locally hosted VLM. It gives sparse guidance, runs on-device, and comes from the ASU LENS Lab's Go2 work on threat levels and safe walking areas. — [ASU FURI PDF](https://forge.engineering.asu.edu/wp-content/uploads/2026/03/Chatterjee_FURI.pdf); [Tech Briefs](https://www.techbriefs.com/component/content/article/53852-an-ai-powered-robodog-is-here-to-save-the-day)
- **GitHub nosixtools/Guide_dog_Unitree_Go1**: a ROS 2 guide-dog stack for the Go1 with navigation, object detection and voice-control launch options. — [GitHub](https://github.com/nosixtools/Guide_dog_Unitree_Go1)
- **CognitiveDog**: a Unitree Go1 with a multimodal LLM. — [ResearchGate](https://www.researchgate.net/publication/377845539_CognitiveDog_Large_Multimodal_Model_Based_System_to_Translate_Vision_and_Language_into_Action_of_Quadruped_Robot)

### Inferences
- Judges who know the field will recognise "Go2 + LLM guide dog" as the Binghamton setup. The pitch needs a clearly different angle.

### Gaps
- My search found no public Go2-specific guide-dog GitHub repo, and no confirmed code release from Binghamton or GenAssist. GitHub API access was unavailable in this session, so I could not do a direct search.

## Q4. What is still unsolved, and what could a 30-hour hackathon still credibly claim as new?

### Takeaway
The core idea is already done. Open edges remain in the following areas:
1. **Real autonomy.** Binghamton still used remote-controlled locomotion.
2. **Safety and trust**, including noise and echolocation, and human-height hazards.
3. **When and how much to talk.** Sparse, on-demand, explainable narration instead of constant chatter.
4. **Finding objects and indoor places in unfamiliar buildings**, using signage and asking people.
5. **Studies with blind users.** RoboFind and Milo report none.

A hackathon can claim a novel integration or interaction design. It cannot claim "first talking robot guide dog."

### Cited Findings
- Binghamton's locomotion was reportedly remote-controlled by an expert. Users rated safety lower, and noise may hinder echolocation. Future work targets more autonomy and longer indoor and outdoor trips. — [Galaxus](https://www.galaxus.de/en/page/guide-dog-20-this-robot-talks-and-guides-you-to-your-destination-42241); [TechXplore](https://techxplore.com/news/2026-04-ai-powered-dogs-dont.html); [aboutaccess](https://aboutaccess.co.uk/robo-dogs-impress-in-trials/)
- Quiet, stable locomotion is a research topic in its own right. — [arXiv 2505.11808](https://arxiv.org/pdf/2505.11808)
- Human-body-height hazards that a dog can pass under are an open problem. — [arXiv 2603.20121](https://arxiv.org/pdf/2603.20121)
- Researchers are deliberately limiting VLM verbosity: it is used only when walking is impossible, to reduce anxiety. Generic GPT-4o scores only 67.1% on guide-dog QA. — [arXiv 2610.03187](https://arxiv.org/abs/2610.03187)
- Explaining why the robot swerved or stopped is an active 2026 topic. — [arXiv 2610.28920](https://arxiv.org/abs/2610.28920)
- Personalised object search ("find my keys" or "my bag", not just any bag) was published in Sep 2026 without a study with blind users. — [arXiv 2609.20330](https://arxiv.org/abs/2609.20330)
- RoboGuide's PI says camera-only systems are limited by line of sight around bends and objects, which favours LiDAR. — [The Engineer](https://theengineer.co.uk/content/news/roboguide-walks-and-talks-to-assist-blind-and-partially-sighted-people)
- Glide already markets an agent that describes scenes and finds objects in line of sight, plus door, elevator and stair finding. Generic "describe the scene" is therefore commercially covered on wheeled platforms. — [glidance.io](https://glidance.io)
- Milo navigates without maps but has no voice or LLM layer. — [Robotics & Automation News](https://roboticsandautomationnews.com/2026/08/04/researchers-unveil-open-source-robotic-guide-dog-designed-to-assist-blind-and-visually-impaired-people/103878/)

### Inferences
These are my synthesis, not claims from the literature. Angles a 30-hour team could defensibly frame as new:
1. **Fully autonomous, LLM-driven wayfinding in an unfamiliar building with no prior map.** The robot reads signs and room numbers with the VLM, asks the user clarifying questions, and builds a semantic map of the route on the fly. This differs from Binghamton, which used a known multi-room environment and teleoperated locomotion, and from Glasgow, which used pre-scanned spaces.
2. **Fusing LiDAR with the VLM for explanations at human height.** For example: "stopping: low-hanging sign at head height, 1.5 m ahead." This combines the co-ego hazard idea with LLM explanation in a live demo.
3. **Narration that is explicitly on demand and scaled to urgency.** Silent by default, with spoken hazard warnings and full descriptions only when asked, measured against constant narration.
4. **Open-vocabulary "find my object or place" on a quadruped with voice teaching**, such as "find the coffee machine" or "find an empty chair." This is a simpler, live counterpart to RoboFind.
5. **A real-time voice-native stack with Grok** (speech to speech plus vision). There is no published guide dog that uses Grok, but that is a novelty of implementation, not of research.

Credibility advice: present the project as building on Binghamton (AAAI 2026) and Glasgow (2024) and cite them. Claim novelty in autonomy, interaction policy or wayfinding, not in the concept itself.

### Gaps
- I found no systematic review from 2025–2026 that lists open problems. The gaps above come from individual papers and press.
- I found no evidence of pilots run with guide dog organisations (Guide Dogs UK, Seeing Eye, Lighthouse) for quadruped robots, beyond RNIB Scotland's involvement with RoboGuide.
- Grok-specific prior art for assistive robots was not searched.
