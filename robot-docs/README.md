# Robot docs and SDKs (downloaded 2026-11-04)

All of these are shallow clones in `sdks/`, which is **git-ignored**. Run `./robot-docs/fetch-sdks.sh` to download them. Each repo's `doc/`, `example/` and README are the documentation.
Official Unitree docs (support.unitree.com/home/en/developer) block scripted downloads, so read them in a browser.

## 🐕 Robot dogs (Unitree): the focus for the guide-dog idea

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

## 🦾 Cobots
| Arm | Repo | Docs |
|---|---|---|
| UFactory xArm 5 | `sdks/xArm-Python-SDK` | `doc/api/xarm_api.md`, `example/wrapper/` |
| UR3e / UR5e | `sdks/ur_rtde` | `doc/`, `examples/py/`. Online: https://sdurobotics.gitlab.io/ur_rtde/ |
| Elite CS63 / CS66 | `sdks/Elite_Robots_CS_SDK` | `doc/`, `example/` |

Official manuals (log in or accept terms on the maker's site): UR → universal-robots.com/download · UFactory → ufactory.cc/download · Elite → elite-robots.com · Unitree → unitree.com/download
