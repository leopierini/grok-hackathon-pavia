# Technical feasibility: drone spots an anomaly, Unitree Go2/Go1 walks there (30-hour hackathon, museum venue)

Local SDK clones referenced below live under
`/Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI Hackathon/robot-docs/sdks/` (abbreviated `SDKS/`). The latest commit dates in the clones: unitree_sdk2_python is 21 Sep 2026 and go2_ros2_sdk is 14 Jul 2026 (from `git log -1`).

---

## Q1. How do you control a Go2 from a laptop and command "walk to point X"? What accuracy and latency can you expect? Is there a usable simulator?

### Takeaway
The quickest route is `unitree_webrtc_connect`. It is pure Python over Wi-Fi, works on AIR/PRO/EDU, needs no ROS, and exposes sport `Move` (velocity), an obstacle-avoidance service, odometry topics, LiDAR and the front camera. Firmware 1.1.15 and later needs a per-device AES key, which can only be fetched with the robot owner's Unitree account. There is no supported high-level "go to (x,y)" command. You have to close the loop yourself on drifting odometry, or try the undocumented obstacle-avoid `mode=2` (absolute position) move. ROS2/Nav2 SLAM is too heavy for 30-minute robot slots in a 1,800 m² venue. The official MuJoCo simulator is low-level only, so it cannot run the sport-mode `Move` API.

### Cited Findings
**unitree_webrtc_connect (legion1581): connection and auth**
- It supports Go2 AIR, PRO and EDU using "the same WebRTC protocol used by the Unitree Go/Unitree Explore mobile apps — no jailbreak or firmware modification required". Install with `pip install unitree_webrtc_connect`, plus `portaudio19-dev`. — `SDKS/go2_webrtc_connect/README.md`; https://github.com/legion1581/unitree_webrtc_connect
- Firmware auth table: Go2 1.0.19–1.1.14 uses a static GCM key that the library handles automatically. Go2 **1.1.15+** uses a per-device AES-128 key (`data2=3`): "Without that key the WebRTC handshake can't decrypt the public key and the connection never starts." — `SDKS/go2_webrtc_connect/README.md`
- Fetch the key with `unitree-fetch-aes-key --email you@example.com --password '...' --device-type Go2`, or with `fetch_aes_key(email, pw, sn=..., device_type="Go2")`. The key is "per device, stable across re-pairings", and the cloud returns it as `dev.key` in `device/bind/list`. You therefore need the credentials of the Unitree account the robot is bound to. — `SDKS/go2_webrtc_connect/README.md`
- Connection modes are `WebRTCConnectionMethod.LocalAP` (laptop joins the robot's Wi-Fi), `LocalSTA` (same LAN, by `ip=` or `serialNumber=`) and `Remote` (via Unitree TURN server, needs account). — `SDKS/go2_webrtc_connect/README.md`
- Typed errors include `RobotBusyError` ("robot rejected — another WebRTC client is connected"). Only one WebRTC client can be connected at a time. — `SDKS/go2_webrtc_connect/README.md`. go2_ros2_sdk also says to "close the connection with a mobile app before connecting to the robot". — `SDKS/go2_ros2_sdk/README.md`
- Go2 features listed: data channel pub/sub and RPC, sport control, video receive, audio send/receive, LiDAR point-cloud decoding, VUI (LED/volume), and an "Obstacle avoidance API". — `SDKS/go2_webrtc_connect/README.md`

**unitree_webrtc_connect: motion commands**
- Switch to normal mode with `publish_request_new(RTC_TOPIC["MOTION_SWITCHER"], {"api_id": 1002, "parameter": {"name": "normal"}})`. Velocity move: `publish_request_new(RTC_TOPIC["SPORT_MOD"], {"api_id": SPORT_CMD["Move"], "parameter": {"x": 0.5, "y": 0, "z": 0}})` (topic `rt/api/sport/request`, `Move`=1008, `StopMove`=1003, `StandUp`=1004, `StandDown`=1005, `RecoveryStand`=1006). — `SDKS/go2_webrtc_connect/examples/go2/data_channel/sportmode/sportmode.py`; `SDKS/go2_webrtc_connect/unitree_webrtc_connect/constants.py`
- Since firmware 1.1.7 there is also an "MCF" api_id space on the same topic (`SPORT_CMD_MCF`, e.g. BackFlip 2043 vs 1044). "Robot must already be in MCF mode (no motion_switcher handshake)." — `SDKS/go2_webrtc_connect/unitree_webrtc_connect/constants.py`
- Obstacle avoidance: topic `rt/api/obstacles_avoid/request`, `OBSTACLES_AVOID_API = {SWITCH_SET:1001, SWITCH_GET:1002, MOVE:1003 {"x","y","yaw","mode":0}, USE_REMOTE_COMMAND_FROM_API:1004}`. The example drives through `rt/wirelesscontroller` joystick messages published at 50 Hz (`{"lx","ly","rx","ry","keys"}`). "When avoidance is on, the obstacle-avoid service intercepts these and applies safety filtering." — `SDKS/go2_webrtc_connect/examples/go2/data_channel/obstacles_avoid/obstacles_avoid.py`; `constants.py`
- Odometry and state topics: `rt/sportmodestate` / `rt/lf/sportmodestate` (fields include `position`, `velocity`, `yaw_speed`, `imu_state.rpy`, `range_obstacle`), `rt/utlidar/robot_pose` (`ROBOTODOM`), `rt/utlidar/voxel_map_compressed` (LiDAR), and `rt/uslam/...` mapping topics (`LIDAR_MAPPING_CMD`, `LIDAR_MAPPING_ODOM`). — `SDKS/go2_webrtc_connect/examples/go2/data_channel/sportmodestate/sportmodestate.py`; `constants.py`
- Video: `conn.video.switchVideoChannel(True)` and `conn.video.add_track_callback(cb)`. Inside the callback, `frame = await track.recv(); img = frame.to_ndarray(format="bgr24")`. — `SDKS/go2_webrtc_connect/examples/go2/video/camera_stream/display_video_channel.py`

**unitree_sdk2_python (official, DDS over Ethernet; EDU)**
- It needs `cyclonedds == 0.10.2` and a network interface name (e.g. `python3 ./example/high_level/sportmode_test.py enp2s0`). Network setup follows https://support.unitree.com/home/en/developer/Quick_start. — `SDKS/unitree_sdk2_python/README.md`
- `SportClient` has `Move(vx, vy, vyaw)`, `StopMove()`, `StandUp()`, `BalanceStand()`, `RecoveryStand()`, `SpeedLevel(level)`, `FreeWalk()`, `FreeAvoid(flag)`, `ClassicWalk(flag)`, `AutoRecoverySet(enabled)`, plus a `PathPoint(timeFromStart, x, y, yaw, vx, vy, vyaw)` type for TrajectoryFollow. — `SDKS/unitree_sdk2_python/unitree_sdk2py/go2/sport/sport_client.py`
- `ObstaclesAvoidClient` has `SwitchSet(on)`, `SwitchGet()`, `Move(vx, vy, vyaw)` (mode 0), `UseRemoteCommandFromApi(bool)`, **`MoveToIncrementPosition(x, y, yaw)` (mode 1)** and **`MoveToAbsolutePosition(x, y, yaw)` (mode 2)**, all sent as api 1003 with no reply. The bundled example only calls them with zeros, and there is no docstring on the frame or the completion semantics. — `SDKS/unitree_sdk2_python/unitree_sdk2py/go2/obstacles_avoid/obstacles_avoid_client.py`; `SDKS/unitree_sdk2_python/example/obstacles_avoid/obstacles_avoid_move.py`
- Front camera example: `example/go2/front_camera/camera_opencv.py <iface>`. — `SDKS/unitree_sdk2_python/README.md`

**go2_ros2_sdk (abizovnuralem): ROS2 + SLAM + Nav2**
- It supports AIR/PRO/EDU over WebRTC or CycloneDDS. Tested on Ubuntu 22.04 with ROS2 humble/iron/rolling. `ros2 launch go2_robot_sdk robot.launch.py` starts the driver, camera, pointcloud_to_laserscan, rviz2, twist_mux, foxglove, `slam_toolbox` and `nav2`. — `SDKS/go2_ros2_sdk/README.md`
- On firmware ≥1.1.15 it needs `ROBOT_AES_KEY` (fetched with unitree-fetch-aes-key). — `SDKS/go2_ros2_sdk/README.md`
- Data rates on firmware 1.1.7: LiDAR "now updates at 7 Hz" and "joint states still arrive at 1 Hz". — `SDKS/go2_ros2_sdk/README.md`
- Workflow: map the space by joystick in rviz, save and serialize the map, then on restart deserialize it from a known "dock" pose and send a `Nav2 Goal`. The README warns that long corridors can distort the map, "the route planner will try to route your dog through walls". Nav2 `controller_frequency: 3.0` and `expected_planner_frequency: 1.0` are set "very conservative" to avoid spinning or no-motion failures. It recommends "following your dog and picking it up when it is about to do something silly". — `SDKS/go2_ros2_sdk/README.md`

**Accuracy and odometry**
- Forum reports say `rt/sportmodestate` "is published only when the MCF (Sport) mode is enabled", and another user saw position and velocity zeroed in Mode 1. — https://forum.mybotshop.de/t/unitree-go2-cannot-echo-sportmodestate/1810
- On Go2-W, community members recommend "FastLio2 or mola or some other lidar based odometry" because the built-in odometry topics were empty. — https://forum.mybotshop.de/t/unitree-go2-w-ros2-odometry-and-topic-availability-issues/1831
- Unitree Go1 docs and the SDK header describe built-in position as "from own odometry in inertial frame, usually drift". — `SDKS/unitree_legged_sdk/include/unitree_legged_sdk/comm.h` (HighState.position)

**Simulators**
- `unitree_mujoco` (official) runs Go2 with `./unitree_mujoco -r go2 -s scene_terrain.xml`, or the Python version. Programs written against unitree_sdk2, unitree_ros2 or unitree_sdk2_python connect unchanged, using DDS domain 1 on loopback instead of domain 0 on the NIC. However, "Current version only supports low-level development", meaning `LowCmd`/`LowState` only, "mainly used for sim to real verification of controller". — https://github.com/westonrobot/unitree_mujoco (mirror of https://github.com/unitreerobotics/unitree_mujoco)
- go2_ros2_sdk carries an "IsaacSim 4.0" badge. — `SDKS/go2_ros2_sdk/README.md`

### Inferences
- For a 30 h build, use `unitree_webrtc_connect` from one Python process: velocity `Move` at about 10–20 Hz, a pose estimate from `rt/sportmodestate.position` or `rt/utlidar/robot_pose`, and a simple "turn to bearing, walk distance, re-check" controller (P-control on heading and distance). Keep obstacle avoidance on via `OBSTACLES_AVOID` SWITCH_SET plus `USE_REMOTE_COMMAND_FROM_API`, and send motion as obstacle-avoid `MOVE` (mode 0) so the safety filter applies. Test `mode=2` (absolute target) and `mode=1` (incremental) in the first robot slot. If either works, it is effectively a built-in "go to X" with avoidance. Its semantics are undocumented, so treat it as a bonus.
- Expect metre-level accuracy, not centimetre-level. Leg odometry drifts with distance and turning (Unitree says "usually drift"). No Go2-specific numbers were found. Plan the demo as short legs of about 5–15 m inside one room. Finish with a visual check (the dog's camera frame sent to the VLM, or a floor marker) instead of relying on odometry to hit the exact spot.
- Motion latency: WebRTC data-channel commands on a local Wi-Fi network should be sub-second. No measured figure was found, so measure it in slot 1.
- Nav2 SLAM is not realistic for this event. Mapping needs manual joystick passes, map quality is fragile in long corridors, and the stack needs Ubuntu 22.04 + ROS2. All of this has to fit into 30-minute supervised slots across three pavilions.
- Simulation fallback for "walk to X": `unitree_mujoco` cannot execute sport `Move` without a separate locomotion policy. A 2D kinematic (unicycle) simulator on the floor plan, behind the same `RobotAdapter.move(vx, vy, vyaw)` / `get_pose()` interface as the real dog, is the most practical way to demo the full loop when the dog isn't available. Isaac Sim is possible but needs an NVIDIA GPU and setup time.

### Gaps
- No measured Go2 odometry drift (m per 10 m), `Move` command latency, or WebRTC video latency was found in any source.
- Semantics of obstacle-avoid `MoveToAbsolutePosition` (mode 2) were not found: which frame, whether it waits for arrival, and whether it works on AIR/PRO over WebRTC.
- Whether the specific venue dog is on firmware ≥1.1.15 (AES key needed) and who owns its Unitree account is unknown.
- Whether `rt/sportmodestate` publishes in normal mode on the latest firmware is unclear. Forum reports conflict with the library's examples.

---

## Q2. If the dog is a Go1: high-level control with unitree_legged_sdk v3.8 and camera access with UnitreecameraSDK. What are the limitations?

### Takeaway
Go1 high-level control is a simple UDP loop at about 500 Hz to `192.168.123.161:8082` using `HighCmd.mode=2` with velocity and yaw speed. Position-target walking (`mode=3`) is marked "reserve", and odometry "usually drift[s]". The cameras are reached by running UnitreecameraSDK on the robot's onboard Jetsons and streaming H.264 over UDP to the laptop. That needs SSH access, killing Unitree's autostart camera processes, and a 192.168.123.x network. It is feasible but noticeably more fiddly than Go2 WebRTC.

### Cited Findings
- unitree_legged_sdk v3.8.6 supports Go1 only. It requires `Legged_sport >= v1.36.0` and firmware ≥ v0.1.35. Build with `cmake -DPYTHON_BUILD=TRUE ..`. Prebuilt Python libs exist for `amd64` and `arm64` (Linux). — `SDKS/unitree_legged_sdk/README.md`; `SDKS/unitree_legged_sdk/lib/python/`
- Python high-level loop: `udp = sdk.UDP(0xee, 8080, "192.168.123.161", 8082)`, `cmd = sdk.HighCmd()`, `state = sdk.HighState()`. Each 2 ms tick it runs `udp.Recv(); udp.GetRecv(state)`, sets fields, then `udp.SetSend(cmd); udp.Send()`. — `SDKS/unitree_legged_sdk/example_py/example_walk.py`
- `HighCmd.mode`: 0 idle, 1 forced stand, "2. target velocity walking (controlled by velocity + yawSpeed)", "3. target position walking (controlled by position + ypr[0]), reserve", "4. path mode walking ... reserve", 5/6 stand down/up, 7 damping. `HighState.position` is "(unit: m), from own odometry in inertial frame, usually drift". — `SDKS/unitree_legged_sdk/include/unitree_legged_sdk/comm.h`
- UnitreecameraSDK 1.1.0 handles stereo depth, color, point clouds and rectified frames. It depends on OpenCV ≥4 with GStreamer. — `SDKS/UnitreecameraSDK/README.md`
- Image transfer: `example_putImagetrans` runs on the robot and sends UDP H.264 to `192.168.123.IpLastSegment` (set in `trans_rect_config.yaml`). Ports 9201–9205 correspond to front, chin, left, right and belly cameras. Before starting, you must stop `Unitree/autostart/02camerarosnode` (and `04imageai` to free compute) with `kill.sh` or `ps ... | xargs kill -9`. The receiver `example_getimagetrans` opens `udpsrc address=192.168.123.<seg> port=...` with `cv2.VideoCapture`. — `SDKS/UnitreecameraSDK/examples/example_putImagetrans.cc`; `SDKS/UnitreecameraSDK/examples/example_getimagetrans.cc`

### Inferences
- With a Go1, implement the same "turn, walk, re-check" controller in `mode=2`. Do not depend on `mode=3`, since it is "reserve" (unimplemented).
- The laptop must be on the 192.168.123.x subnet, via Ethernet or Go1 Wi-Fi. The prebuilt `.so` files are Linux-only (amd64/arm64), so a macOS laptop needs a Linux VM, Docker or a second Linux laptop.
- Go1 camera access means SSH into the onboard computers and killing vendor processes. Do it only if staff allow it during a slot. Otherwise skip the dog camera and let the drone or a handheld phone provide the "investigation" view.

### Gaps
- The Go1 onboard SSH credentials and IPs for the camera Jetsons are not in the local READMEs. Whether museum staff permit modifying autostart processes is unknown.
- No Go1 obstacle-avoidance API is exposed in legged_sdk v3.8. Go1 has ultrasonic sensors, but the SDK exposure was not verified.

---

## Q3. Drones: which candidate (Tello/Tello EDU, DJI Mini, Crazyflie) is practical for indoor flight with video streamed to a laptop?

### Takeaway
The DJI Tello (EDU) is the only candidate that a team can program from a laptop in hours. It has a UDP text SDK, the djitellopy Python library, 720p video to the laptop, mission pads for indoor localization (EDU only), and it weighs about 80 g. Its limits are about 13 minutes of flight, a need for good light and floor texture, and video that only works when the laptop joins the drone's own Wi-Fi AP. DJI Mini drones need an Android/iOS MSDK v5 app, which is unrealistic in 30 h. A Crazyflie needs a positioning deck plus an AI-deck camera that streams only low-resolution grayscale.

### Cited Findings
**Tello / Tello EDU**
- Specs: about 80 g (including props and battery), 13 min max flight time, 8 m/s max speed, 100 m max distance, 5 MP photo, 720p30 video, 82.6° FOV, 1.1 Ah/3.8 V battery, built-in vision positioning system. — https://www.ryzerobotics.com/tello/specs
- SDK transport: Tello at `192.168.10.1`. Commands go to UDP port 8889, and you send `command` then `streamon`. Video is received on UDP port 11111, state on port 8890 (SDK 3.0). Mission-pad commands are `mon`, `moff` and `mdirection x` (0 down, 1 forward, 2 both). Pads are m1–m8, and EDU with SDK 2.0 is required. — Tello SDK 2.0 User Guide https://xcopter.com/download/Tello%20SDK%202.0%20User%20Guide.pdf ; Mission Pad User Guide https://xcopter.com/download/Tello%20Mission%20Pad%20User%20Guide.pdf ; SDK 3.0 https://xcopter.com/download/Tello_SDK_3.0_User_Guide_en.pdf. These details come from search snippets because the PDFs were not fetched in full. A third-party page (harleylara/tello-js) describes conflicting `mon`/`mdirection` semantics.
- djitellopy (`pip install djitellopy`) supports Tello and Tello EDU, Python ≥3.6. "Mission pad detection and navigation is only supported by the Tello EDU." "Mission pads need a bright environment to work reliably." — https://github.com/damiafuentes/DJITelloPy
- djitellopy API: `connect()`, `streamon()`, `get_frame_read(with_queue=False, max_queue_len=32) -> BackgroundFrameRead`, `send_rc_control(lr, fb, ud, yaw)` (each −100..100), `go_xyz_speed(x,y,z,speed)` (x/y/z −500..500 cm, speed 10–100 cm/s), `go_xyz_speed_mid(x,y,z,speed,mid)` (mid 1–8), `move_forward(x)` (20–500 cm), `enable_mission_pads()`, `set_mission_pad_detection_direction(x)` ("both" gives 10 Hz detection, otherwise 20 Hz), `get_mission_pad_id()` (−1 if none), `get_mission_pad_distance_x/y/z()` (cm), `get_battery()`, `get_height()`, `get_distance_tof()`, `set_video_resolution('low'|'high')`, `set_video_fps('low'|'middle'|'high')` = 5/15/30 fps, `set_video_bitrate(0..5)`, and `connect_to_wifi(ssid, pw)` (EDU only, reboots). — https://djitellopy.readthedocs.io/en/latest/tello/
- **Video only works in AP mode**: `streamon` is "supported in AP mode, not on EDUs joined to a Wi-Fi network". The README repeats that video is unavailable once the drone joins an existing Wi-Fi network. EDU swarm (`TelloSwarm`, `simple-swarm.py`) requires station mode, so a swarm loses video. — https://djitellopy.readthedocs.io/en/latest/tello/ ; https://github.com/damiafuentes/DJITelloPy

**DJI Mini**
- DJI MSDK v5.13.0 (17 Mar 2025) added the Mini 4 Pro, "only with RC-N2"; the DJI RC 2 controller is not supported. Mini 3 and Mini 3 Pro are in the MSDK v5 compatibility tables. No official MSDK support for the Mini 5 / Mini 5 Pro was found as of a May 2026 forum thread. — https://developer.dji.com/doc/mobile-sdk-tutorial/en ; https://dronedj.com/2025/03/21/dji-mini-4-pro-msdk/ ; https://forum.flylitchi.com/t/dji-released-the-api-for-mini-5-pro/28370

**Crazyflie**
- Position commands (`takeoff/land/go_to`) are "unusable" without a Flow deck v2, Lighthouse, Loco or mocap. Flow deck v2 range is up to 4 m. Lighthouse precision is "typically lower than 1 cm". The Crazyflie 2.1 has no magnetometer, so yaw drifts. The AI deck streams over Wi-Fi at about 8 Hz, 324×244 mono8. — https://github.com/rewire-run/crazyflie-example ; https://micro-502.readthedocs.io/en/latest/assignment/hardware_quickstart.html ; https://www.bitcraze.io/category/random/page/23/

### Inferences
- Prefer a Tello EDU if one is available, since it adds mission pads. A plain Tello still works if you use fixed-route flight plus visual markers. Expect about 8–10 minutes of usable flight per battery indoors, so bring several batteries and a charging hub.
- Networking is the main Tello gotcha. Video needs the laptop on the Tello's AP, while the Go2 (STA mode on venue Wi-Fi, or its own AP) and the xAI API (internet) need other links. Plan for a USB Wi-Fi adapter (one radio on the Tello AP, one on the venue/Go2 network), or two laptops bridged over Ethernet or a local socket. Skip the EDU swarm, because station mode kills video.
- DJI Mini: do not build an MSDK app in 30 h. If only a Mini is available, fly it manually with DJI Fly, record or screen-capture the video to a laptop (HDMI/USB capture of the phone, or post-flight file transfer), and run analysis on that. The handoff then has to be zone-based (see Q4).
- Crazyflie: skip it unless it already has Flow/Lighthouse and AI decks fitted. Low-resolution grayscale video is poor input for VLM anomaly detection.

### Gaps
- Tello vision-positioning operating height and light requirements were not on the spec page, so verify them in the Tello user manual. Museum lighting (often dim, with glossy or uniform floors) may degrade the VPS and mission-pad detection.
- No measured Tello video latency to the laptop was found.
- Whether Tello EDU kits include mission pads, or whether the venue's drones are EDU at all, is unknown.

---

## Q4. Air-to-ground target handoff without GPS: which method is most robust in 30 hours?

### Takeaway
The most robust option is a **shared floor-plan map with named zones and waypoints**, where the drone's detection is reported as a zone, not raw coordinates. You can upgrade to metric coordinates with ArUco/AprilTag markers at surveyed floor positions and an image-to-floor homography when the drone can see the floor. Mission pads (Tello EDU) can anchor the drone's own position. The dog navigates on its own odometry from a known start pose, with obstacle avoidance on, and confirms visually on arrival.

### Cited Findings
- Tello EDU mission pads give pad ID (1–8) and the drone's x/y/z offset from the pad in cm via `get_mission_pad_id()` and `get_mission_pad_distance_x/y/z()`. Downward-only detection runs at 20 Hz. Pads need bright light. — https://djitellopy.readthedocs.io/en/latest/tello/ ; https://github.com/damiafuentes/DJITelloPy
- `go_xyz_speed_mid(x,y,z,speed,mid)` flies to coordinates in a mission pad's frame, so the drone's route can be defined relative to pads at known floor locations. — https://djitellopy.readthedocs.io/en/latest/tello/
- Tello camera FOV is 82.6°. — https://www.ryzerobotics.com/tello/specs
- The go2_ros2_sdk approach depends on starting the dog at a marked "dock" pose so that it has "a high quality initial position and angle" relative to a map. — `SDKS/go2_ros2_sdk/README.md`
- Go2 and Go1 position feedback comes from odometry that drifts. — `SDKS/unitree_legged_sdk/include/unitree_legged_sdk/comm.h`; https://forum.mybotshop.de/t/unitree-go2-w-ros2-odometry-and-topic-availability-issues/1831

### Inferences
Options ranked for 30 h robustness, most to least:
1. **Named zones on a shared floor plan.** Define one coordinate frame for the demo room with origin at a taped "dock" where the dog starts. Draw zones A–F as polygons with a waypoint at each centroid, in a JSON file. The drone flies a fixed route (e.g. `move_forward`/`rotate_clockwise` legs, or `go_xyz_speed_mid` over pads). Each route segment is tagged with the zone it overlooks, so a detection during segment k means zone k. The handoff message is `{zone: "C", waypoint: [x,y], evidence: frame.jpg, description: "..."}`. The dog then runs `goto(waypoint)`. This tolerates drone drift of a couple of metres and is simple enough to build in about 2–3 hours.
2. **Floor markers + homography (metric upgrade).** Place 4+ ArUco/AprilTag markers (printed A4) at surveyed floor coordinates within the camera view. With the Tello's forward camera tilted down, or the drone pitched/positioned to see the floor, detect markers with OpenCV `cv2.aruco`, compute `cv2.findHomography(img_pts, floor_pts)`, and project the anomaly bounding-box bottom-centre to floor (x,y). This gives sub-metre accuracy when markers are visible but fails when they are occluded or the light is poor. The same markers can serve the dog's final visual approach.
3. **Mission pads (EDU only).** They are good for anchoring the drone's position over known pads, but the pads are only m1–m8 and need bright light. They tell you where the drone is, not where the anomaly is, so combine them with option 1 (pad ↔ zone).
4. **Drone hovering over the target as a beacon** for the dog to visually servo toward. This is impressive but hard: the dog's camera would have to track a small drone, and it adds collision risk. Not recommended.
- Note for the Tello: the main camera faces forward, so seeing the floor requires flying at about 1–2 m and looking ahead and down at a distance. The "downward" sensor on EDU is used only for pad detection via `mdirection`. Zone-by-route is therefore more natural than a strict top-down homography.
- Keep the demo to one room or a corridor of about 10×15 m with 4–6 zones. Do not attempt cross-pavilion navigation.

### Gaps
- No published hackathon-scale Tello→quadruped handoff paper or blog was found, so the rankings are engineering judgement.
- Whether the Tello's forward camera sees enough floor area at typical hover heights for a usable homography was not verified with a source.

---

## Q5. Vision: running Grok vision (xAI API) on drone frames for anomaly detection, latency, and pre-filtering with a local detector

### Takeaway
xAI's API accepts JPEG/PNG images (≤20 MiB) as base64 data URLs through the OpenAI-compatible `https://api.x.ai/v1/responses` endpoint. The current docs show `grok-4.7` as the example model. Latency is not documented and will be seconds per call for a reasoning model. So the VLM should be gated: a fast local detector or frame-diff runs on every frame, and only candidate frames (about 0.5–1 per second at most) go to Grok for semantic judgement and a description.

### Cited Findings
- Image input: formats `jpg/jpeg` and `png`, max 20 MiB per image, "no stated limit on the number of images". Pass `image_url` as `"data:image/jpeg;base64,<...>"` or a public URL, inside `content` items of type `input_image` and `input_text`. The examples use `"detail": "high"`. — https://docs.x.ai/docs/guides/image-understanding
- Endpoints and SDKs: REST `https://api.x.ai/v1/responses`; OpenAI SDK with `base_url="https://api.x.ai/v1"`; xAI Python SDK `client.chat.create(model="grok-4.7")` with `image(image_url=..., detail="high")`; Vercel AI SDK `xai.responses('grok-4.7')`. — https://docs.x.ai/docs/guides/image-understanding
- The docs raise timeouts for reasoning models (3600 s in Python examples) and advise against storing server-side history when sending images. No latency or per-image token cost is stated. — https://docs.x.ai/docs/guides/image-understanding
- The quickstart confirms Grok accepts text and images, with examples sending `input_image` plus text to the Responses endpoint. — https://docs.x.ai/developers/quickstart.md
- Tello video can be lowered to 480p / 5–15 fps with `set_video_resolution`, `set_video_fps` and `set_video_bitrate` to reduce Wi-Fi load. — https://djitellopy.readthedocs.io/en/latest/tello/
- go2_ros2_sdk ships a `coco_detector` node (TorchVision) publishing `Detection2DArray` on `/detected_objects`, with configurable `device:=cuda` and `detection_threshold`. — `SDKS/go2_ros2_sdk/README.md`

### Inferences
- Pipeline: Tello frames (about 15–30 fps) go to a local filter. The filter is one of: (a) YOLOv8/YOLO11 or YOLO-World with an open-vocabulary prompt such as "person lying on floor, bag, backpack, fire, smoke, open door, fallen object"; (b) a background or reference-frame diff per zone, by comparing the current patrol pass with a "clean" pass; or both. Candidate frames are JPEG-encoded at about 1024 px and sent to Grok with a structured-output prompt: `{"anomaly": bool, "type": str, "confidence": 0-1, "bbox": [...], "description": str}`. Run the VLM asynchronously so flight control never blocks on it.
- Budget about 2–8 s per Grok call, then verify with a quick benchmark on day 1. Use the fastest non-reasoning or "fast" vision-capable Grok variant listed on docs.x.ai/models if one exists. On a laptop CPU, a small YOLO model runs at roughly real-time on 480p. Apple-silicon `mps` makes this comfortable.
- Plant a staged anomaly (e.g. an abandoned bag or a "person lying down" played by a teammate) so detection is reliable in the demo. Avoid relying on subtle anomalies against museum exhibits, where false positives are likely.
- Reuse the same Grok call on the dog's camera frame at arrival ("Is there a [bag] in front of the robot? Describe it") to close the loop: "investigate and confirm".

### Gaps
- No official xAI latency figures, rate limits or per-image token costs were found on the image-understanding page. Check docs.x.ai models and rate-limit pages, and benchmark.
- No sources were collected on YOLO-World speed on a MacBook; this is engineering judgement only.

---

## Q6. Safety and rules: flying drones indoors in a museum with historic exhibits (prop guards, weight class) and EU rules for indoor flight

### Takeaway
EU drone regulation 2019/947 is generally described as not applying to UAS operated exclusively indoors. National rules (security, privacy) and, above all, the museum's own permission still apply. With an 80 g Tello, prop guards, low altitude, a no-fly buffer around exhibits and staff spotters, the main risks are collision with artefacts and hitting people. Those are handled by geofencing in software, keeping to a cleared zone, and keeping a manual kill or land ready.

### Cited Findings
- EASA presentation slides say Regulation 2019/947 "Does not apply to UAS operated exclusively indoors". A Maltese transport authority summary says the same. — https://uic.org/events/IMG/pdf/2_drone_regulation_easa.pdf ; https://www.transport.gov.mt/UAS-Regulations-Summary.pdf-f5935
- An Italian industry article says the indoor exclusion appears in the Guidance Material, GM1 to Article 1. — https://www.dronezine.it/?p=86281
- Member States may impose conditions for reasons outside the scope of Regulation 2018/1139, "including public security or protection of privacy and personal data". — via search summary of https://www.easa.europa.eu/en/document-library/easy-access-rules/online-publications/easy-access-rules-unmanned-aircraft-systems
- Tello weight is about 80 g. — https://www.ryzerobotics.com/tello/specs
- For the dog, go2_ros2_sdk advises "following your dog and picking it up when it is about to do something silly", and warns about routing into walls with bad maps. — `SDKS/go2_ros2_sdk/README.md`

### Inferences
- The legal risk is low because the event is indoors, but **venue permission and staff conditions are the real gate**. Agree a flight box (e.g. one cleared hall), a maximum height of about 2 m, a minimum distance of about 2–3 m from exhibits and glass cases, and no flights over visitors. Mark the box on the floor plan and enforce it in software: reject drone commands that would leave the box, and auto-land on low battery (`get_battery()` < 20%) or lost video.
- Keep a hardware kill path. Send `emergency` / `land` from a dedicated key, or have the Tello app or a spare operator ready. For the dog, staff should hold the physical remote. Note that the Unitree phone app cannot be connected at the same time as the WebRTC script (`RobotBusyError`).
- Sub-250 g drones carry the lowest risk class under EU rules (C0 / legacy <250 g). That is not legally required indoors, but it is a useful argument with museum staff.
- Privacy: frames sent to an external API (xAI) may contain visitors' faces. Tell staff, avoid storing frames, or blur faces before upload.

### Gaps
- The primary EUR-Lex text (Art. 2 / GM1 Art. 1 of 2019/947) was not fetched, so the indoor exclusion is sourced from secondary EASA and authority slides. The specific EU member state of the venue, and its national indoor rules, are unknown.
- The C0 class marking applicability to the (pre-2024) Tello was not verified with a source.
- Whether the Tello ships with prop guards was not confirmed from the spec page.

---

## Q7. Recommended minimal architecture, what is realistic versus too hard in 30 h, main failure risks, and fallbacks

### Takeaway
Build a single-laptop Python orchestrator around three adapters: `DroneAdapter` (djitellopy), `DogAdapter` (unitree_webrtc_connect, or legged_sdk for Go1) and `Brain` (local YOLO filter plus Grok). They share a JSON floor-plan of zones. Each adapter gets a simulated twin (a recorded drone video replayer, and a 2D kinematic dog on the floor plan) so the full loop can be developed and demoed without the robot. Use the 30-minute dog slots only for tightly scripted hardware integration tests.

### Cited Findings
- Dog control primitives available: `SPORT_CMD["Move"]` velocity, `OBSTACLES_AVOID` switch and move, `rt/sportmodestate` position, video via `conn.video.add_track_callback`. — `SDKS/go2_webrtc_connect/README.md` and examples
- Drone primitives: `connect`, `streamon`, `get_frame_read`, `takeoff`, `move_*`, `go_xyz_speed(_mid)`, `land`, mission pads. — https://djitellopy.readthedocs.io/en/latest/tello/
- unitree_mujoco is low-level only, so it cannot act as a drop-in sim for sport `Move`. — https://github.com/westonrobot/unitree_mujoco
- AES key is required on Go2 firmware ≥1.1.15 and is fetched with the owner's Unitree credentials. — `SDKS/go2_webrtc_connect/README.md`
- Only one WebRTC client is allowed (`RobotBusyError`). — `SDKS/go2_webrtc_connect/README.md`
- Tello video is unavailable when the EDU is in station mode. — https://djitellopy.readthedocs.io/en/latest/tello/

### Inferences
**Minimal architecture (single repo, Python 3.11, asyncio):**
1. `floorplan.json`: room polygon, dog dock pose (0,0,0°), zones {id, polygon, waypoint}, drone patrol route as a list of {action, zone_id}.
2. `drone.py`: `TelloDrone` (real) and `ReplayDrone` (plays a recorded MP4 with a route-segment timeline). Methods: `start_patrol()`, `frames()` async generator yielding (frame, zone_id, t), and `land()`.
3. `brain.py`: per-frame YOLO / frame-diff gate. Gated frames go to Grok vision through the Responses API with a JSON-schema prompt, producing an `AnomalyEvent{zone, waypoint, desc, image}`. Debounce by requiring 2 hits in the same zone.
4. `dog.py`: `Go2WebRTCDog` (real), `Go1UdpDog` (if Go1) and `SimDog` (unicycle model). Methods: `stand()`, `get_pose()`, `goto(x,y)` (rotate-then-walk P-controller at 10–20 Hz, obstacle avoidance on, timeout plus stop), `snapshot()`, `stop()`.
5. `orchestrator.py` state machine: PATROL → ANOMALY_FOUND → DISPATCH_DOG → DOG_ARRIVED → CONFIRM (Grok on the dog's frame) → REPORT. Add a small web dashboard (FastAPI + a canvas floor-plan) showing the drone route, the zone highlight, the dog's position trace and the evidence images. The dashboard is what the judges see.

**Realistic in 30 h:** Tello scripted patrol with video; YOLO plus Grok anomaly detection on staged anomalies; zone-based handoff; Go2 walking to a waypoint within about 1 m over 5–15 m in one cleared room using odometry and obstacle avoidance; dog-camera confirmation with Grok; dashboard; sim and replay fallbacks.

**Too hard or high-risk in 30 h:** SLAM/Nav2 mapping of the 1,800 m² museum or multi-pavilion navigation; autonomous drone navigation across rooms; real-time drone tracking by the dog; precise (<20 cm) metric handoff; DJI Mini MSDK app development; Crazyflie with positioning decks; Tello EDU swarm with video; low-level/RL control in MuJoCo or Isaac Sim.

**Main failure risks and mitigations:**
- *No Go2 connection on the day* (AES key, owner's account, firmware, app still connected, Wi-Fi mode). Before the event, ask staff for the firmware version, the serial number, and either the AES key (`unitree-fetch-aes-key`) or the account login. Use the first slot only to confirm `connect()` plus a `Move` plus a state read.
- *Wi-Fi conflicts.* The Tello needs its own AP for video, while the Go2 and internet need other links. Bring a USB Wi-Fi dongle or a second laptop, and test the full network topology without the dog using `SimDog`.
- *Odometry drift or the dog missing the spot.* Keep legs short, start every run from the taped dock, and end with a visual confirmation that accepts "within the zone".
- *Tello drift, lighting, battery.* Keep the route short (about 2–3 minutes), use mission pads only if lighting is bright, keep several batteries charged, and auto-land below 20%.
- *VLM latency or false positives.* Gate with a local detector, call asynchronously, use staged anomalies, and cache responses for the replay demo.
- *Limited robot time (30-minute slots).* Prepare scripted test checklists per slot and record everything: Go2 video, pose logs, drone video. Those recordings become the replay fallback.
- *Safety or staff veto.* Agree the flight box and dog route with staff early, and keep emergency stop paths ready (`land`/`emergency`, `StopMove`/`StandDown`).

**Fallback ladder:** (1) Full live: drone, dog and Grok. (2) Live dog with replayed drone video (recorded the same day over the same zones). (3) Live drone with `SimDog` on the dashboard, plus a pre-recorded clip of the real dog executing `goto`. (4) Fully replayed: recorded drone and dog videos with the live Grok calls and the dashboard.

### Gaps
- How many 30-minute dog slots the team gets, and whether the dog is a Go2 AIR, PRO or EDU or a Go1, is unknown. That determines whether the DDS/EDU path, and Go2's LiDAR obstacle avoidance, are available.
- No end-to-end latency measurements exist for this exact pipeline. All timing figures above are estimates to benchmark on day 1.
