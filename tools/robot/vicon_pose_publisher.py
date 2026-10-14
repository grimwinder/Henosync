#!/usr/bin/env python3
"""
vicon_pose_publisher.py — onboard VICON pose source for henosync_controller.py.

Runs on the robot and reads its own pose straight from the VICON PC, using the
same values as Henosync's core vicon_manager (object root segment, mm → m and
yaw from the global Euler Z angle), so the pose is in the same frame as the
waypoints Henosync sends. With the controller started as
`--pose_topic /<ns>/henosync/onboard_pose`, the robot keeps driving its path
while the rosbridge link to Henosync is down — like an onboard GPS.

Vicon ships no Python package for Linux, only the C++ SDK library, so the
VICON reading is done by the small vicon_stream program (vicon_stream.cpp,
built on the robot — see tools/robot/README.md). This node runs it, restarts
it if the VICON connection drops, and publishes the newest pose it printed.

Occluded frames are skipped (vicon_stream prints nothing for them); the
controller's pose watchdog stops the robot if occlusion lasts longer than its
timeout.

Topics published:
  /<ns>/henosync/onboard_pose   geometry_msgs/Pose2D — x, y (m), theta (rad)

Usage:
  python3 vicon_pose_publisher.py --vicon_host 192.168.11.3 --object jackal
                                  [--namespace j100_0364] [--rate 50]
                                  [--stream_bin ~/vicon_stream]
"""

import argparse
import os
import socket
import subprocess
import threading
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose2D

RESTART_DELAY_S = 2.0


def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    # The SDK's Connect() can crash on an unreachable host (same guard as
    # Henosync's vicon_manager) — check with a plain socket first.
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class ViconPosePublisher(Node):
    def __init__(self, namespace: str, vicon_host: str, vicon_port: int,
                 object_name: str, rate: float, stream_bin: str):
        super().__init__("vicon_pose_publisher")
        topic = f"/{namespace}/henosync/onboard_pose" if namespace else "/henosync/onboard_pose"
        self._pub = self.create_publisher(Pose2D, topic, 10)
        self._host = vicon_host
        self._port = vicon_port
        self._object = object_name
        self._stream_bin = stream_bin

        self._lock = threading.Lock()
        self._latest: tuple[float, float, float] | None = None
        self._running = True

        self._reader = threading.Thread(target=self._stream_loop, daemon=True)
        self._reader.start()
        self._timer = self.create_timer(1.0 / rate, self._publish_latest)
        self.get_logger().info(
            f"vicon_pose_publisher — {vicon_host}:{vicon_port} object='{object_name}' "
            f"→ {topic} @ {rate:.0f} Hz"
        )

    def _stream_loop(self) -> None:
        """Run vicon_stream, read its pose lines, restart it if it exits."""
        addr = f"{self._host}:{self._port}" if self._port != 801 else self._host
        while self._running:
            if not _tcp_reachable(self._host, self._port):
                self.get_logger().warning(
                    f"VICON {self._host}:{self._port} unreachable — retrying",
                    throttle_duration_sec=5.0,
                )
                time.sleep(RESTART_DELAY_S)
                continue

            try:
                proc = subprocess.Popen(
                    [self._stream_bin, addr, self._object],
                    stdout=subprocess.PIPE, text=True,
                )
            except OSError as e:
                self.get_logger().error(
                    f"Cannot run {self._stream_bin}: {e} — build it first (see tools/robot/README.md)"
                )
                return

            for line in proc.stdout:
                parts = line.split()
                if len(parts) != 3:
                    continue
                with self._lock:
                    self._latest = (float(parts[0]), float(parts[1]), float(parts[2]))
                if not self._running:
                    break

            proc.kill()
            proc.wait()
            if self._running:
                self.get_logger().warning("vicon_stream exited — restarting")
                time.sleep(RESTART_DELAY_S)

    def _publish_latest(self) -> None:
        with self._lock:
            latest, self._latest = self._latest, None
        if latest is None:
            return  # no new frame since last publish (occluded or disconnected)
        msg = Pose2D()
        msg.x, msg.y, msg.theta = latest
        self._pub.publish(msg)

    def stop(self) -> None:
        self._running = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish this robot's VICON pose for henosync_controller")
    parser.add_argument("--vicon_host", required=True, help="IP of the VICON PC.")
    parser.add_argument("--vicon_port", type=int, default=801)
    parser.add_argument("--object", required=True, help="VICON object name — same as the Henosync device config.")
    parser.add_argument("--namespace", default="", help="ROS2 namespace prefix. No slashes.")
    parser.add_argument("--rate", type=float, default=50.0, help="Publish rate in Hz.")
    parser.add_argument("--stream_bin", default=os.path.expanduser("~/vicon_stream"),
                        help="Path to the built vicon_stream program.")
    args, _ = parser.parse_known_args()

    rclpy.init()
    node = ViconPosePublisher(
        namespace=args.namespace.strip("/"), vicon_host=args.vicon_host,
        vicon_port=args.vicon_port, object_name=args.object, rate=args.rate,
        stream_bin=os.path.expanduser(args.stream_bin),
    )
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
