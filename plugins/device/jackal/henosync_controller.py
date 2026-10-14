#!/usr/bin/env python3
"""
henosync_controller.py — onboard proportional velocity controller for Henosync.

Run this ROS2 node on the robot when the "Onboard Controller" capability is
selected in Henosync.  Henosync publishes the target waypoint (or a whole
path of waypoints); this node runs the control loop locally against a pose
topic and reports progress back.

The pose can come from anywhere that publishes geometry_msgs/Pose2D in the
same frame as the waypoints (--pose_topic):
  - Henosync's relay (default): /<ns>/henosync/vicon_pose, forwarded over
    rosbridge — the robot stops if the link to Henosync drops.
  - vicon_pose_publisher.py running on the robot (--pose_topic
    /<ns>/henosync/onboard_pose): the robot reads VICON itself, so it keeps
    driving its path while the link to Henosync is down.

If no pose arrives for POSE_TIMEOUT_S the robot stops and waits — it never
drives on a stale position.

Robot log: the controller records its own account of what it does — its pose
and the velocity it commands (SAMPLE_HZ while a path is active), waypoint
arrivals, path start/end, pose loss, and when Henosync's heartbeat stops and
resumes (link_lost / link_restored). Records are numbered and re-sent on
henosync/robot_log until Henosync acknowledges them, so whatever happened
while the link was down reaches Henosync once it is back. Every record is
also appended to ~/henosync_logs/ on the robot, in case it never comes back.

Topics subscribed:
  /<ns>/henosync/waypoint      std_msgs/String  — JSON, one of:
                                 {"x": m, "y": m, "arrival_radius": m, "max_speed": m/s}
                                 {"path_id": str, "run_id": str, "path": [{"x": m, "y": m}, ...],
                                  "arrival_radius": m, "max_speed": m/s}
                                 {"stop": true}
  <pose_topic>                 geometry_msgs/Pose2D — x, y (m), theta (rad)
  /<ns>/henosync/heartbeat     std_msgs/String  — sent by Henosync at 2 Hz while connected
  /<ns>/henosync/robot_log_ack std_msgs/String  — JSON {"boot", "seq"}: records up to seq received

Topics published:
  <cmd_vel_topic>              geometry_msgs/TwistStamped (default)
                               geometry_msgs/Twist         (--unstamped)
  /<ns>/henosync/arrived       std_msgs/Bool — True when the last waypoint is reached
  /<ns>/henosync/progress      std_msgs/String — JSON {"path_id", "completed",
                               "total", "done", "stopped"}; sent on every
                               waypoint reached and re-sent at 1 Hz so Henosync
                               catches up after a reconnect
  /<ns>/henosync/robot_log     std_msgs/String — JSON {"boot", "sent", "records":
                               [{"seq", "t", "kind", "path_id", "run_id", ...}]};
                               unacknowledged records, oldest first, at LOG_SEND_HZ

Usage:
  python henosync_controller.py [--namespace tb2] [--unstamped]
                                [--cmd_vel_topic /tb2/cmd_vel]
                                [--pose_topic /tb2/henosync/onboard_pose]
"""

import argparse
import collections
import json
import math
import os
import time
import uuid
from datetime import datetime

import rclpy
from geometry_msgs.msg import Pose2D, Twist, TwistStamped
from rclpy.node import Node
from std_msgs.msg import Bool, String

# ── Controller constants ───────────────────────────────────────────────────────

MAX_LINEAR_VEL: float = 0.3   # m/s  — hard cap regardless of max_speed from Henosync
MAX_ANGULAR_VEL: float = 1.5  # rad/s
LINEAR_GAIN: float = 0.5
ANGULAR_GAIN: float = 1.2
ANGULAR_DEADBAND: float = 0.05  # rad — ignore heading errors below this threshold
CTRL_HZ: float = 10.0
POSE_TIMEOUT_S: float = 1.5   # stop if no pose received for this long (relay sends at 2 Hz)
PROGRESS_HZ: float = 1.0

# ── Robot log constants ────────────────────────────────────────────────────────

LINK_TIMEOUT_S: float = 2.0   # no Henosync heartbeat (2 Hz) for this long → link lost
SAMPLE_HZ: float = 2.0        # pose + command samples while a path is active
LOG_SEND_HZ: float = 2.0
LOG_CHUNK: int = 200          # records per robot_log message
LOG_DIR = os.path.expanduser("~/henosync_logs")


class HenosyncController(Node):
    def __init__(self, namespace: str, cmd_vel_topic: str, pose_topic: str, unstamped: bool):
        super().__init__("henosync_controller")

        self._ns = namespace
        self._unstamped = unstamped

        # Topic names — namespace prefix applied to henosync topics only
        def _ht(path: str) -> str:
            return f"/{namespace}/{path}" if namespace else f"/{path}"

        pose_topic = pose_topic or _ht("henosync/vicon_pose")
        self._pose_topic = pose_topic

        self._waypoint_sub = self.create_subscription(
            String, _ht("henosync/waypoint"), self._on_waypoint, 10
        )
        self._pose_sub = self.create_subscription(
            Pose2D, pose_topic, self._on_pose, 10
        )
        self._heartbeat_sub = self.create_subscription(
            String, _ht("henosync/heartbeat"), self._on_heartbeat, 10
        )
        self._log_ack_sub = self.create_subscription(
            String, _ht("henosync/robot_log_ack"), self._on_log_ack, 10
        )
        self._arrived_pub = self.create_publisher(Bool, _ht("henosync/arrived"), 10)
        self._progress_pub = self.create_publisher(String, _ht("henosync/progress"), 10)
        self._log_pub = self.create_publisher(String, _ht("henosync/robot_log"), 10)

        if unstamped:
            self._cmd_vel_pub = self.create_publisher(Twist, cmd_vel_topic, 10)
        else:
            self._cmd_vel_pub = self.create_publisher(TwistStamped, cmd_vel_topic, 10)

        # Path state — a single waypoint is a path of length 1
        self._path: list[tuple[float, float]] = []
        self._path_id: str = ""
        self._run_id: str = ""
        self._index: int = 0
        self._stopped: bool = False
        self._arrival_radius: float = 0.1
        self._max_speed: float = MAX_LINEAR_VEL
        self._active: bool = False  # True while waypoints remain

        self._pos_x: float = 0.0
        self._pos_y: float = 0.0
        self._pos_theta: float = 0.0
        self._last_pose_time: float = 0.0
        self._pose_stale_logged: bool = False
        self._cmd: tuple[float, float] = (0.0, 0.0)  # last velocity commanded

        # Link to Henosync, judged by its heartbeat
        self._link_up: bool = False
        self._last_heartbeat: float = 0.0       # monotonic
        self._last_heartbeat_wall: float = 0.0  # epoch, for the log

        # Robot log — unacknowledged records, oldest first
        self._boot = uuid.uuid4().hex[:8]
        self._seq = 0
        self._unacked: collections.deque = collections.deque()
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path = os.path.join(LOG_DIR, f"{stamp}_{self._boot}.jsonl")
        self._log_file = open(self._log_path, "a", buffering=1)
        self._tick = 0

        self._timer = self.create_timer(1.0 / CTRL_HZ, self._control_tick)
        self._progress_timer = self.create_timer(1.0 / PROGRESS_HZ, self._publish_progress)
        self._log_timer = self.create_timer(1.0 / LOG_SEND_HZ, self._send_log)
        self._log(
            "controller_start", pose_topic=pose_topic, cmd_vel_topic=cmd_vel_topic,
            log_file=self._log_path,
        )
        self.get_logger().info(
            f"henosync_controller ready — ns='{namespace}', "
            f"cmd_vel={cmd_vel_topic}, pose={pose_topic}, unstamped={unstamped}, "
            f"log={self._log_path}"
        )

    # ── Robot log ──────────────────────────────────────────────────────────────

    def _log(self, kind: str, **fields) -> None:
        self._seq += 1
        record = {
            "seq": self._seq, "t": time.time(), "kind": kind,
            "path_id": self._path_id, "run_id": self._run_id, **fields,
        }
        self._unacked.append(record)
        self._log_file.write(json.dumps({"boot": self._boot, **record}) + "\n")

    def _send_log(self) -> None:
        if not self._unacked:
            return
        msg = String()
        msg.data = json.dumps({
            "boot": self._boot,
            "sent": time.time(),
            "records": [self._unacked[i] for i in range(min(LOG_CHUNK, len(self._unacked)))],
        })
        self._log_pub.publish(msg)

    def _on_log_ack(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        if data.get("boot") != self._boot:
            return
        acked = int(data.get("seq", 0))
        while self._unacked and self._unacked[0]["seq"] <= acked:
            self._unacked.popleft()

    def _on_heartbeat(self, msg: String) -> None:
        now = time.monotonic()
        if not self._link_up:
            if self._last_heartbeat_wall:
                self._log(
                    "link_restored",
                    down_s=round(time.time() - self._last_heartbeat_wall, 3),
                    backlog=len(self._unacked),
                )
                self.get_logger().info(
                    f"Henosync link restored — sending {len(self._unacked)} logged record(s)"
                )
            else:
                self._log("link_up")
            self._link_up = True
        self._last_heartbeat = now
        self._last_heartbeat_wall = time.time()

    def _check_link(self) -> None:
        if self._link_up and time.monotonic() - self._last_heartbeat > LINK_TIMEOUT_S:
            self._link_up = False
            self._log("link_lost", last_heartbeat_t=self._last_heartbeat_wall)
            self.get_logger().warning(
                "Henosync link lost — "
                + ("continuing path on onboard controller" if self._active else "no path active")
            )

    def _log_sample(self) -> None:
        pose_ok = time.monotonic() - self._last_pose_time <= POSE_TIMEOUT_S
        self._log(
            "sample",
            x=round(self._pos_x, 4), y=round(self._pos_y, 4), theta=round(self._pos_theta, 4),
            v=round(self._cmd[0], 4), w=round(self._cmd[1], 4),
            wp=self._index, link=self._link_up, pose_ok=pose_ok,
        )

    # ── Waypoints and pose ─────────────────────────────────────────────────────

    def _on_waypoint(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f"Invalid waypoint JSON: {msg.data!r}")
            return

        if data.get("stop", False):
            if self._active:
                self._log("path_stopped", completed=self._index, total=len(self._path))
            self._active = False
            self._stopped = True
            self._publish_zero()
            self._publish_progress()
            self.get_logger().info("Stop sentinel received — stopping")
            return

        if "path" in data:
            path = [(float(p["x"]), float(p["y"])) for p in data["path"]]
        else:
            path = [(float(data.get("x", 0.0)), float(data.get("y", 0.0)))]

        self._path = path
        self._path_id = str(data.get("path_id", ""))
        self._run_id = str(data.get("run_id", ""))
        self._index = 0
        self._stopped = False
        self._arrival_radius = float(data.get("arrival_radius", 0.1))
        self._max_speed = min(float(data.get("max_speed", MAX_LINEAR_VEL)), MAX_LINEAR_VEL)
        self._active = bool(path)
        self._log(
            "path_start", total=len(path), path=[[x, y] for x, y in path],
            arrival_radius=self._arrival_radius, max_speed=self._max_speed,
            pose_topic=self._pose_topic,
        )
        self.get_logger().info(
            f"New path '{self._path_id}': {len(path)} waypoint(s), first "
            f"({path[0][0]:.3f}, {path[0][1]:.3f}) "
            f"radius={self._arrival_radius:.3f}m speed={self._max_speed:.3f}m/s"
        )
        self._publish_progress()

    def _on_pose(self, msg: Pose2D) -> None:
        self._pos_x = msg.x
        self._pos_y = msg.y
        self._pos_theta = msg.theta
        self._last_pose_time = time.monotonic()

    # ── Control loop ───────────────────────────────────────────────────────────

    def _control_tick(self) -> None:
        self._check_link()
        if not self._active:
            return
        self._tick += 1
        if self._tick % max(1, round(CTRL_HZ / SAMPLE_HZ)) == 0:
            self._log_sample()

        if time.monotonic() - self._last_pose_time > POSE_TIMEOUT_S:
            # Never drive on a stale position — hold until the pose comes back.
            self._publish_zero()
            if not self._pose_stale_logged:
                self._pose_stale_logged = True
                self._log("pose_stale")
                self.get_logger().warning(
                    f"No pose for {POSE_TIMEOUT_S:.1f}s — holding position"
                )
            return
        if self._pose_stale_logged:
            self._pose_stale_logged = False
            self._log("pose_restored")
            self.get_logger().info("Pose restored — resuming")

        target_x, target_y = self._path[self._index]
        dx = target_x - self._pos_x
        dy = target_y - self._pos_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < self._arrival_radius:
            self._log(
                "waypoint", index=self._index, x=round(self._pos_x, 4), y=round(self._pos_y, 4),
                dist=round(distance, 4), link=self._link_up,
            )
            self._index += 1
            self.get_logger().info(
                f"Reached waypoint {self._index}/{len(self._path)} "
                f"({target_x:.3f}, {target_y:.3f}), dist={distance:.3f}m"
            )
            if self._index >= len(self._path):
                self._active = False
                self._publish_zero()
                self._log("path_done", total=len(self._path), link=self._link_up)
                arrived = Bool()
                arrived.data = True
                self._arrived_pub.publish(arrived)
            self._publish_progress()
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

    def _publish_progress(self) -> None:
        if not self._path:
            return
        msg = String()
        msg.data = json.dumps({
            "path_id": self._path_id,
            "completed": self._index,
            "total": len(self._path),
            "done": self._index >= len(self._path),
            "stopped": self._stopped,
        })
        self._progress_pub.publish(msg)

    def _publish_velocity(self, linear: float, angular: float) -> None:
        self._cmd = (linear, angular)
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
        "--pose_topic", default=None,
        help="Pose2D topic to steer by. Defaults to Henosync's relay, /<ns>/henosync/vicon_pose. "
             "Use /<ns>/henosync/onboard_pose with vicon_pose_publisher.py to keep "
             "driving while the link to Henosync is down."
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
    node = HenosyncController(
        namespace=ns, cmd_vel_topic=cmd_vel, pose_topic=args.pose_topic,
        unstamped=args.unstamped,
    )
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
