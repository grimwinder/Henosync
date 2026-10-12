#!/usr/bin/env python3
"""
henosync_controller.py — onboard proportional velocity controller for Henosync.

Run this ROS2 node on the robot when the "Onboard Controller" capability is
selected in Henosync.  Henosync publishes the target waypoint and the current
VICON position; this node runs the control loop locally and publishes `arrived`
when the robot reaches the target.

This keeps the control loop on the robot side, avoiding latency from
rosbridge round-trips in the default Henosync velocity controller.

Topics subscribed:
  /<ns>/henosync/waypoint      std_msgs/String  — JSON: {"x": m, "y": m,
                                                          "arrival_radius": m,
                                                          "max_speed": m/s}
                                                  OR    {"stop": true}
  /<ns>/henosync/vicon_pose    geometry_msgs/Pose2D — x, y (m), theta (rad)

Topics published:
  <cmd_vel_topic>              geometry_msgs/TwistStamped (default)
                               geometry_msgs/Twist         (--unstamped)
  /<ns>/henosync/arrived       std_msgs/Bool — True when within arrival_radius

Usage:
  ros2 run <your_pkg> henosync_controller  [--namespace tb2] [--unstamped]
  python henosync_controller.py            [--namespace tb2] [--unstamped]
                                           [--cmd_vel_topic /tb2/cmd_vel]
"""

import argparse
import json
import math
import sys

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose2D, Twist, TwistStamped
from std_msgs.msg import Bool, String


# ── Controller constants ───────────────────────────────────────────────────────

MAX_LINEAR_VEL: float = 0.3   # m/s  — hard cap regardless of max_speed from Henosync
MAX_ANGULAR_VEL: float = 1.5  # rad/s
LINEAR_GAIN: float = 0.5
ANGULAR_GAIN: float = 1.2
ANGULAR_DEADBAND: float = 0.05  # rad — ignore heading errors below this threshold
CTRL_HZ: float = 10.0


class HenosyncController(Node):
    def __init__(self, namespace: str, cmd_vel_topic: str, unstamped: bool):
        super().__init__("henosync_controller")

        self._ns = namespace
        self._unstamped = unstamped

        # Topic names — namespace prefix applied to henosync topics only
        def _ht(path: str) -> str:
            return f"/{namespace}/{path}" if namespace else f"/{path}"

        self._waypoint_sub = self.create_subscription(
            String, _ht("henosync/waypoint"), self._on_waypoint, 10
        )
        self._pose_sub = self.create_subscription(
            Pose2D, _ht("henosync/vicon_pose"), self._on_vicon_pose, 10
        )
        self._arrived_pub = self.create_publisher(Bool, _ht("henosync/arrived"), 10)

        if unstamped:
            self._cmd_vel_pub = self.create_publisher(Twist, cmd_vel_topic, 10)
        else:
            self._cmd_vel_pub = self.create_publisher(TwistStamped, cmd_vel_topic, 10)

        # Controller state
        self._target_x: float = 0.0
        self._target_y: float = 0.0
        self._arrival_radius: float = 0.1
        self._max_speed: float = MAX_LINEAR_VEL
        self._active: bool = False  # True when a waypoint is pending

        self._pos_x: float = 0.0
        self._pos_y: float = 0.0
        self._pos_theta: float = 0.0

        self._timer = self.create_timer(1.0 / CTRL_HZ, self._control_tick)
        self.get_logger().info(
            f"henosync_controller ready — ns='{namespace}', "
            f"cmd_vel={cmd_vel_topic}, unstamped={unstamped}"
        )

    def _on_waypoint(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f"Invalid waypoint JSON: {msg.data!r}")
            return

        if data.get("stop", False):
            self._active = False
            self._publish_zero()
            self.get_logger().info("Stop sentinel received — stopping")
            return

        self._target_x = float(data.get("x", 0.0))
        self._target_y = float(data.get("y", 0.0))
        self._arrival_radius = float(data.get("arrival_radius", 0.1))
        self._max_speed = min(float(data.get("max_speed", MAX_LINEAR_VEL)), MAX_LINEAR_VEL)
        self._active = True
        self.get_logger().info(
            f"New waypoint: ({self._target_x:.3f}, {self._target_y:.3f}) "
            f"radius={self._arrival_radius:.3f}m speed={self._max_speed:.3f}m/s"
        )

    def _on_vicon_pose(self, msg: Pose2D) -> None:
        self._pos_x = msg.x
        self._pos_y = msg.y
        self._pos_theta = msg.theta

    def _control_tick(self) -> None:
        if not self._active:
            return

        dx = self._target_x - self._pos_x
        dy = self._target_y - self._pos_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < self._arrival_radius:
            self._active = False
            self._publish_zero()
            arrived = Bool()
            arrived.data = True
            self._arrived_pub.publish(arrived)
            self.get_logger().info(
                f"Arrived at ({self._target_x:.3f}, {self._target_y:.3f}), "
                f"dist={distance:.3f}m"
            )
            return

        bearing = math.atan2(dy, dx)
        heading_error = math.atan2(
            math.sin(bearing - self._pos_theta),
            math.cos(bearing - self._pos_theta),
        )

        linear = min(
            self._max_speed,
            LINEAR_GAIN * distance * max(0.0, math.cos(heading_error)),
        )
        if abs(heading_error) < ANGULAR_DEADBAND:
            angular = 0.0
        else:
            angular = max(
                -MAX_ANGULAR_VEL,
                min(MAX_ANGULAR_VEL, ANGULAR_GAIN * heading_error),
            )

        self._publish_velocity(linear, angular)

    def _publish_velocity(self, linear: float, angular: float) -> None:
        if self._unstamped:
            msg = Twist()
            msg.linear.x = linear
            msg.angular.z = angular
        else:
            msg = TwistStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.twist.linear.x = linear
            msg.twist.angular.z = angular
        self._cmd_vel_pub.publish(msg)

    def _publish_zero(self) -> None:
        self._publish_velocity(0.0, 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Henosync onboard controller node")
    parser.add_argument(
        "--namespace", default="",
        help="ROS2 namespace prefix (e.g. tb2 → /tb2/henosync/waypoint). No slashes."
    )
    parser.add_argument(
        "--cmd_vel_topic", default=None,
        help="cmd_vel topic to publish to. Defaults to /<ns>/cmd_vel or /cmd_vel."
    )
    parser.add_argument(
        "--unstamped", action="store_true",
        help="Publish geometry_msgs/Twist instead of TwistStamped (e.g. for Jackal)."
    )
    # rclpy passes its own args after --ros-args; strip them out
    args, _ = parser.parse_known_args()

    ns = args.namespace.strip("/")
    if args.cmd_vel_topic:
        cmd_vel = args.cmd_vel_topic
    else:
        cmd_vel = f"/{ns}/cmd_vel" if ns else "/cmd_vel"

    rclpy.init()
    node = HenosyncController(namespace=ns, cmd_vel_topic=cmd_vel, unstamped=args.unstamped)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
