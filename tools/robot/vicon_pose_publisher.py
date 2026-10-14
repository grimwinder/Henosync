#!/usr/bin/env python3
"""
vicon_pose_publisher.py — onboard VICON pose source for henosync_controller.py.

Runs on the robot and reads its own pose straight from the VICON DataStream
SDK, the same way Henosync's core vicon_manager does (same object, root
segment, mm → m and yaw from the global Euler Z angle), so the pose is in
the same frame as the waypoints Henosync sends. With the controller started
as `--pose_topic /<ns>/henosync/onboard_pose`, the robot keeps driving its
path while the rosbridge link to Henosync is down — like an onboard GPS.

Occluded frames are skipped rather than published; the controller's pose
watchdog stops the robot if occlusion lasts longer than its timeout.

Topics published:
  /<ns>/henosync/onboard_pose   geometry_msgs/Pose2D — x, y (m), theta (rad)

Requires the VICON DataStream SDK Python package (vicon_dssdk) on the robot,
and network access from the robot to the VICON PC (port 801).

Usage:
  python vicon_pose_publisher.py --vicon_host 192.168.10.1 --object jackal
                                 [--namespace j100_0364] [--rate 50]
"""

import argparse
import socket

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose2D

from vicon_dssdk import ViconDataStream


def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    # The SDK's Connect() can crash the process on an unreachable host
    # (same guard as Henosync's vicon_manager) — check with a plain socket first.
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class ViconPosePublisher(Node):
    def __init__(self, namespace: str, vicon_host: str, vicon_port: int, object_name: str, rate: float):
        super().__init__("vicon_pose_publisher")
        topic = f"/{namespace}/henosync/onboard_pose" if namespace else "/henosync/onboard_pose"
        self._pub = self.create_publisher(Pose2D, topic, 10)
        self._object = object_name
        self._host = vicon_host
        self._port = vicon_port
        self._client = None
        self._timer = self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f"vicon_pose_publisher — {vicon_host}:{vicon_port} object='{object_name}' → {topic} @ {rate:.0f} Hz"
        )

    def _connect(self) -> bool:
        if not _tcp_reachable(self._host, self._port):
            self.get_logger().warning(
                f"VICON {self._host}:{self._port} unreachable — retrying", throttle_duration_sec=5.0
            )
            return False
        client = ViconDataStream.Client()
        addr = f"{self._host}:{self._port}" if self._port != 801 else self._host
        client.Connect(addr)
        client.EnableSegmentData()
        client.SetStreamMode(ViconDataStream.Client.StreamMode.EClientPull)
        self._client = client
        self.get_logger().info("Connected to VICON")
        return True

    def _tick(self) -> None:
        if self._client is None and not self._connect():
            return
        try:
            if not self._client.GetFrame():
                return
            segment = self._client.GetSubjectRootSegmentName(self._object)
            translation, occluded = self._client.GetSegmentGlobalTranslation(self._object, segment)
            if occluded:
                return
            rotation, _ = self._client.GetSegmentGlobalRotationEulerXYZ(self._object, segment)
        except ViconDataStream.DataStreamException as e:
            self.get_logger().warning(f"VICON read failed: {e}", throttle_duration_sec=5.0)
            if not self._client.IsConnected():
                self._client = None
            return

        msg = Pose2D()
        msg.x = translation[0] / 1000.0
        msg.y = translation[1] / 1000.0
        msg.theta = rotation[2]
        self._pub.publish(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish this robot's VICON pose for henosync_controller")
    parser.add_argument("--vicon_host", required=True, help="IP of the VICON PC.")
    parser.add_argument("--vicon_port", type=int, default=801)
    parser.add_argument("--object", required=True, help="VICON object name — same as the Henosync device config.")
    parser.add_argument("--namespace", default="", help="ROS2 namespace prefix. No slashes.")
    parser.add_argument("--rate", type=float, default=50.0, help="Publish rate in Hz.")
    args, _ = parser.parse_known_args()

    rclpy.init()
    node = ViconPosePublisher(
        namespace=args.namespace.strip("/"), vicon_host=args.vicon_host,
        vicon_port=args.vicon_port, object_name=args.object, rate=args.rate,
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
