import sys
import time

import rclpy
from geometry_msgs.msg import PointStamped
from sensor_msgs.msg import Joy
from std_msgs.msg import Int8


def main():
    x = float(sys.argv[1])
    y = float(sys.argv[2])
    rclpy.init()
    node = rclpy.create_node("go2_goal")
    joy_pub = node.create_publisher(Joy, "/joy", 5)
    goal_pub = node.create_publisher(PointStamped, "/goal_point", 5)
    stop_pub = node.create_publisher(Int8, "/stop", 5)
    time.sleep(0.3)
    clear = Int8()
    clear.data = 0
    joy = Joy()
    joy.header.frame_id = "goalpoint_tool"
    # axes[2] < -0.1 turns autonomy on. axes[4] stays 0 so speed comes from the planner.
    joy.axes = [0.0, 0.0, -1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    joy.buttons = [0] * 11
    goal = PointStamped()
    goal.header.frame_id = "map"
    goal.point.x = x
    goal.point.y = y
    for _ in range(3):
        now = node.get_clock().now().to_msg()
        joy.header.stamp = now
        goal.header.stamp = now
        joy_pub.publish(joy)
        stop_pub.publish(clear)
        goal_pub.publish(goal)
        time.sleep(0.05)
    time.sleep(0.2)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
