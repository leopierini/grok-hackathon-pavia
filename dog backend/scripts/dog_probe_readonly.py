"""Read-only Go2 probe: connect, read status, save one camera frame, disconnect.

Sends NO motion commands, NO settings changes, NO firmware/system requests.
The only messages sent are the library's connection handshake/heartbeat and the
session-only "video on" switch needed to receive camera frames.

Usage:
    .venv/bin/python scripts/dog_probe_readonly.py [--ip 192.168.123.161] [--out evidence/dog]
"""

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import cv2
from unitree_webrtc_connect.constants import RTC_TOPIC
from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)

HARD_TIMEOUT_S = 40
LISTEN_S = 8


async def probe(ip: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report: dict = {"ip": ip, "started": stamp, "topics": {}, "photo": None}
    start = time.monotonic()
    first_frame: list = []

    conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)
    t0 = time.monotonic()
    await conn.connect()
    report["connect_s"] = round(time.monotonic() - t0, 2)
    print(f"[probe] connected in {report['connect_s']} s")

    def make_cb(name):
        def cb(msg):
            entry = report["topics"].setdefault(name, {"count": 0})
            entry["count"] += 1
            if "first" not in entry:
                entry["first"] = msg.get("data")
                entry["first_at_s"] = round(time.monotonic() - start, 2)
        return cb

    # Read-only subscriptions.
    for name in ("LF_SPORT_MOD_STATE", "LOW_STATE", "MULTIPLE_STATE"):
        conn.datachannel.pub_sub.subscribe(RTC_TOPIC[name], make_cb(name))

    # Video: session-only switch so the dog streams frames to us.
    async def on_track(track):
        while not first_frame:
            frame = await track.recv()
            first_frame.append(frame.to_ndarray(format="bgr24"))

    conn.video.add_track_callback(on_track)
    conn.video.switchVideoChannel(True)

    deadline = time.monotonic() + LISTEN_S
    while time.monotonic() < deadline:
        await asyncio.sleep(0.25)

    if first_frame:
        img = first_frame[0]
        path = out_dir / f"go2_frame_{stamp}.jpg"
        tmp = path.with_suffix(".tmp.jpg")
        cv2.imwrite(str(tmp), img)
        tmp.rename(path)
        report["photo"] = str(path.resolve())
        report["frame_shape"] = list(img.shape)
        print(f"[probe] saved frame {img.shape} -> {path}")
    else:
        print("[probe] no video frame received")

    conn.video.switchVideoChannel(False)
    await conn.disconnect()
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default="192.168.123.161")
    ap.add_argument("--out", default="evidence/dog")
    args = ap.parse_args()
    out_dir = Path(args.out)

    try:
        report = asyncio.run(asyncio.wait_for(probe(args.ip, out_dir), HARD_TIMEOUT_S))
    except asyncio.TimeoutError:
        print(f"[probe] hard timeout after {HARD_TIMEOUT_S} s")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    rpath = out_dir / f"probe_{report['started']}.json"
    rpath.write_text(json.dumps(report, indent=2, default=str))
    print(f"[probe] report -> {rpath}")
    for name, t in report["topics"].items():
        print(f"[probe] {name}: {t['count']} msgs, first after {t.get('first_at_s')} s")


if __name__ == "__main__":
    main()
