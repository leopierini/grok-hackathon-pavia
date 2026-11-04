# Robot docs and SDKs (downloaded 2026-11-04)

All of these are shallow clones in `sdks/`, which is **git-ignored**. Run `./robot-docs/fetch-sdks.sh` to download them. Each repo's `doc/`, `example/` and README are the documentation.
Official Unitree docs (support.unitree.com/home/en/developer) block scripted downloads, so read them in a browser.

## 🐕 Robot dogs (Unitree)

### Go2: the best fit
| Repo | What | Key paths |
|---|---|---|
| `sdks/go2_webrtc_connect` | **Easiest route.** Same WebRTC protocol as the Unitree app. Works on **AIR/PRO/EDU**, no jailbreak. `pip install unitree_webrtc_connect` | `examples/go2/video/camera_stream` (front camera) · `examples/go2/audio/live_audio`, `mp3_player` (**dog speaker + mic, two-way**) · `examples/go2/data_channel/obstacles_avoid` · `.../lidar` · `.../sportmode` (walk, stand, move) · `.../vui` (LED, volume) · `examples/fetch_aes_key.py` |
| `sdks/unitree_sdk2_python` | Official SDK over DDS/Ethernet (**full features need the EDU variant**) | `unitree_sdk2py/go2/{sport,video,vui,obstacles_avoid,robot_state}` · `example/go2/high_level/go2_sport_client.py` · `example/go2/front_camera/` |
| `sdks/go2_ros2_sdk` | ROS2 driver (WebRTC or CycloneDDS): SLAM, Nav2, LiDAR, camera, foxglove | README |

⚠️ **Go2 firmware ≥ 1.1.15 needs a per-device AES-128 key** for the LAN WebRTC handshake (`fetch_aes_key.py`, which uses the Unitree account the dog is bound to). Ask museum staff for the firmware version and account.

### Go1
| Repo | What |
|---|---|
| `sdks/unitree_legged_sdk` (branch `go1`, v3.8.6) | High- and low-level control over UDP; Python wrapper in `python_wrapper/`, examples in `example_py/` |
| `sdks/UnitreecameraSDK` | Go1's onboard stereo cameras (they run on the dog's internal Jetson boards) |

The Go1 has no easy two-way audio or camera from a laptop, so prefer the Go2.

## 🚁 Drone: DJI/Ryze Tello EDU (Global), confirmed on site (made 2020/12)
| Resource | What |
|---|---|
| `tello/Tello SDK 2.0 User Guide.pdf` | Official command reference: UDP 8889 for commands, 8890 for state, 11111 for video |
| `tello/Tello Mission Pad User Guide.pdf` | Mission pads give **indoor localization** (EDU only, needs good light) |
| `sdks/DJITelloPy` | Python lib `pip install djitellopy`: `Tello().connect()`, `takeoff()`, `go_xyz_speed_mid()`, `get_frame_read()`, `enable_mission_pads()` · examples in `examples/` |

Key commands: `command`, `takeoff`, `land`, `emergency`, `streamon`, `go x y z speed [mid]` (move relative to a mission pad), `mon` (enable pad detection), `mdirection 0|1|2` (pad camera: down, forward, both), `rc a b c d`, `ap ssid pass` (**station mode**: joins a router; the SDK says swarm, community reports video doesn't work in this mode).
⚠️ **Network:** for video, the laptop must join the Tello's own Wi-Fi, so it needs a **second interface** (USB Wi-Fi or Ethernet) or a second laptop for internet, Grok and the dog. Flight time is about 13 min per battery.

## 🦾 Cobots
| Arm | Repo | Docs |
|---|---|---|
| UFactory xArm 5 | `sdks/xArm-Python-SDK` | `doc/api/xarm_api.md`, `example/wrapper/` |
| UR3e / UR5e | `sdks/ur_rtde` | `doc/`, `examples/py/`. Online: https://sdurobotics.gitlab.io/ur_rtde/ |
| Elite CS63 / CS66 | `sdks/Elite_Robots_CS_SDK` | `doc/`, `example/` |

Official manuals (log in or accept terms on the maker's site): UR → universal-robots.com/download · UFactory → ufactory.cc/download · Elite → elite-robots.com · Unitree → unitree.com/download
