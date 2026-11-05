import time

import rclpy
from sensor_msgs.msg import Joy
from std_msgs.msg import Int8


def main():
    rclpy.init()
    node = rclpy.create_node("go2_stop")
    joy_pub = node.create_publisher(Joy, "/joy", 5)
    stop_pub = node.create_publisher(Int8, "/stop", 5)
    time.sleep(0.3)
    joy = Joy()
    joy.header.frame_id = "goalpoint_tool"
    # axes[2] > -0.1 drops autonomy. axes[5] stays above -0.1 so manual drive stays off.
    # buttons[4] stays 0: that button wipes the route planner's graph.
    joy.axes = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    joy.buttons = [0] * 11
    stop = Int8()
    stop.data = 15  # block forward, back, and both yaws
    for _ in range(5):
        joy.header.stamp = node.get_clock().now().to_msg()
        joy_pub.publish(joy)
        stop_pub.publish(stop)
        time.sleep(0.05)
    time.sleep(0.2)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
