#!/usr/bin/env python3
"""findDrone and returnHome. A goal uses the same Joy as the RViz Goalpoint tool.

The walk is the oblivious RSSI rule used on robots with one omnidirectional
antenna (Oliveira, ISR 2010; the ESP32 access-point followers): one step,
then a fresh reading. Stronger keeps the heading, weaker turns around,
a change under 2 dB takes a new heading. A spin in place is the ARREST
method and needs a directional antenna, which this Pi does not have.
"""
import math
import random
import sys
import threading
import time
from pathlib import Path

HOME = Path("/tmp/go2-home.yaml")
RSSI = Path("/Users/ares-pc/localrepo/grok-hackathon-pavia/robot/go2/rssi.dbm")
GOAL_AXES = [0.0, 0.0, -1.0, 0.0, 1.0, 1.0, 0.0, 0.0]
GOAL_BUTTONS = [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0]


def wrap(angle):
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def yaw_of(q):
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


def step_point(x, y, yaw):
    return x + math.cos(yaw), y + math.sin(yaw)


def heading_after(delta, heading, turn):
    """Oblivious rule from the omni-antenna RSSI walkers: keep, reverse, or turn."""
    if delta >= 2.0:
        return heading
    if delta <= -2.0:
        return wrap(heading + math.pi)
    return wrap(heading + turn)


def sane(x, y):
    return abs(x) < 30 and abs(y) < 30


def _selftest():
    assert wrap(3.5) < 0
    assert heading_after(3.0, 0.4, 1.0) == 0.4
    assert abs(abs(heading_after(-3.0, 0.0, 1.0)) - math.pi) < 1e-9
    assert abs(heading_after(0.5, 0.0, math.pi / 2) - math.pi / 2) < 1e-9
    x, y = step_point(0.0, 0.0, 0.0)
    assert abs(x - 1.0) < 1e-9 and abs(y) < 1e-9
    assert sane(1, -2) and not sane(-3932, 0)
    print("ok")


def main():
    import rclpy
    from geometry_msgs.msg import PointStamped
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from sensor_msgs.msg import Joy
    from std_msgs.msg import Empty, Float32, Int8
    from std_srvs.srv import Trigger

    class Seek(Node):
        def __init__(self):
            super().__init__("go2_seek")
            self.lock = threading.Lock()
            self.x = self.y = self.z = self.yaw = None
            self.prev = None
            self.stop = 0
            self.rssi = None
            self.rssi_at = 0.0
            self.busy = False
            self.create_subscription(Odometry, "/state_estimation", self.on_odom, 10)
            self.create_subscription(Int8, "/stop", self.on_stop, 10)
            self.create_subscription(Float32, "/rssi", self.on_rssi, 10)
            self.joy_pub = self.create_publisher(Joy, "/joy", 5)
            self.goal_pub = self.create_publisher(PointStamped, "/goal_point", 5)
            self.create_service(Trigger, "/find_drone", self.on_find)
            self.create_subscription(Empty, "/find_drone_go", self.on_go, 5)
            self.create_service(Trigger, "/return_home", self.on_home)
            self.get_logger().info("find_drone and return_home ready")

        def on_odom(self, msg):
            p = msg.pose.pose.position
            yaw = yaw_of(msg.pose.pose.orientation)
            with self.lock:
                if (
                    not HOME.exists()
                    and self.prev is not None
                    and sane(p.x, p.y)
                    and abs(p.x - self.prev[0]) < 0.05
                    and abs(p.y - self.prev[1]) < 0.05
                ):
                    HOME.write_text(f"x: {p.x}\ny: {p.y}\nyaw: {yaw}\n")
                    self.get_logger().info(f"home {p.x:.2f} {p.y:.2f}")
                self.prev = (p.x, p.y)
                self.x, self.y, self.z, self.yaw = p.x, p.y, p.z, yaw

        def on_stop(self, msg):
            self.stop = int(msg.data)

        def on_rssi(self, msg):
            self.rssi = float(msg.data)
            self.rssi_at = time.time()

        def pose(self):
            with self.lock:
                return self.x, self.y, self.z, self.yaw

        def halted(self):
            return self.stop == 15

        def wait_fresh(self, since, timeout=30):
            end = time.time() + timeout
            while time.time() < end:
                if self.halted():
                    return None
                if self.rssi is not None and self.rssi_at > since:
                    return self.rssi
                try:
                    if RSSI.stat().st_mtime > since:
                        return float(RSSI.read_text().strip())
                except (OSError, ValueError):
                    pass
                time.sleep(0.3)
            return None

        def send_goal(self, x, y):
            _, _, z, _ = self.pose()
            joy = Joy()
            joy.header.frame_id = "goalpoint_tool"
            joy.axes = list(GOAL_AXES)
            joy.buttons = list(GOAL_BUTTONS)
            goal = PointStamped()
            goal.header.frame_id = "map"
            goal.point.x = float(x)
            goal.point.y = float(y)
            goal.point.z = 0.0 if z is None else float(z)
            for _ in range(2):
                now = self.get_clock().now().to_msg()
                joy.header.stamp = now
                goal.header.stamp = now
                self.joy_pub.publish(joy)
                self.goal_pub.publish(goal)
                time.sleep(0.05)

        def wait_near(self, x, y):
            end = time.time() + 25
            while time.time() < end:
                if self.halted():
                    return False
                px, py, _, _ = self.pose()
                if px is not None and math.hypot(px - x, py - y) < 0.45:
                    return True
                time.sleep(0.2)
            return False

        def on_go(self, _msg):
            self.stop = 0
            self.begin()

        def begin(self):
            x, y, _, _ = self.pose()
            if self.busy or x is None or not sane(x, y):
                return False
            self.busy = True
            threading.Thread(target=self.search, daemon=True).start()
            return True

        def on_find(self, _req, resp):
            if self.busy:
                resp.success = True
                resp.message = "already"
                return resp
            if self.halted():
                resp.success = False
                resp.message = "stopped"
                return resp
            if not self.begin():
                resp.success = False
                resp.message = "no pose"
                return resp
            resp.success = True
            resp.message = "started"
            return resp

        def search(self):
            try:
                heading = self.pose()[3]
                if heading is None:
                    return
                prev = self.wait_fresh(time.time())
                if prev is None:
                    self.get_logger().error("no rssi")
                    return
                if prev >= -40.0 and self._close_enough(prev):
                    return
                for _ in range(12):
                    if self.halted():
                        return
                    x, y, _, _ = self.pose()
                    if x is None:
                        return
                    gx, gy = step_point(x, y, heading)
                    started = time.time()
                    self.get_logger().info(f"step {gx:.2f} {gy:.2f} {prev:.0f} dBm")
                    self.send_goal(gx, gy)
                    self.wait_near(gx, gy)
                    reading = self.wait_fresh(started)
                    if reading is None:
                        self.get_logger().error("no fresh rssi")
                        return
                    if reading >= -40.0 and self._close_enough(reading):
                        return
                    heading = heading_after(reading - prev, heading, random.uniform(-math.pi, math.pi))
                    self.get_logger().info(f"rssi {prev:.0f} -> {reading:.0f}")
                    prev = reading
            finally:
                self.busy = False

        def _close_enough(self, first):
            # Three fresh samples at or above -40 dBm, as the beacon walkers do.
            # A dip under -48 throws the count away.
            count = 1
            since = time.time()
            while count < 3:
                if self.halted():
                    return False
                reading = self.wait_fresh(since)
                if reading is None:
                    return False
                since = time.time()
                if reading >= -40.0:
                    count += 1
                elif reading < -48.0:
                    return False
            self.get_logger().info(f"arrived {first:.0f} dBm")
            return True

        def on_home(self, _req, resp):
            if self.halted():
                resp.success = False
                resp.message = "stopped"
                return resp
            try:
                vals = {}
                for line in HOME.read_text().splitlines():
                    key, value = line.split(":")
                    vals[key.strip()] = float(value)
                x, y = vals["x"], vals["y"]
            except (OSError, ValueError, KeyError):
                resp.success = False
                resp.message = "no home"
                return resp
            if not sane(x, y):
                resp.success = False
                resp.message = "no home"
                return resp
            self.send_goal(x, y)
            resp.success = True
            resp.message = f"{x:.2f} {y:.2f}"
            return resp

    rclpy.init()
    node = Seek()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
    else:
        main()
