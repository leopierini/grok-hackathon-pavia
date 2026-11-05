import json
import math
import struct
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2


class Watch(Node):
    def __init__(self):
        super().__init__("go2_pose_watch")
        self.last = 0.0
        self.cloud_at = 0.0
        self.pts = []
        self.create_subscription(Odometry, "/state_estimation", self.on_pose, 10)
        self.create_subscription(PointCloud2, "/registered_scan", self.on_cloud, 5)

    def on_cloud(self, msg):
        now = time.monotonic()
        if now - self.cloud_at < 0.4:
            return
        self.cloud_at = now
        step = msg.point_step
        n = msg.width * msg.height
        raw = memoryview(bytes(msg.data))
        pts = []
        for i in range(n):
            x, y = struct.unpack_from("<ff", raw, i * step)
            if x != x or y != y:
                continue
            pts.append((round(x, 2), round(y, 2)))
        self.pts = pts

    def on_pose(self, msg):
        now = time.monotonic()
        if now - self.last < 0.2:
            return
        self.last = now
        q = msg.pose.pose.orientation
        p = msg.pose.pose.position
        yaw = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )
        print(
            json.dumps({"x": p.x, "y": p.y, "yaw": yaw, "pts": self.pts}),
            flush=True,
        )


def main():
    rclpy.init()
    node = Watch()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
