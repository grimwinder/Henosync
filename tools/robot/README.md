# Robot-side scripts

Henosync runs on your laptop and talks to each robot over **rosbridge**. For most
features that's all you need: no Henosync code runs on the robot.

The **Onboard Controller** capability is the exception. With it, the robot drives
itself to the waypoints Henosync sends, so these scripts must be copied to the
robot's computer and run there:

| Script                   | What it does                                                                                                                                           | Needed for                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------- |
| `henosync_controller.py` | Receives waypoints (or a whole path) from Henosync and drives the robot to them with a proportional controller. Reports progress back to Henosync. | Onboard Controller capability (any mode)      |
| `vicon_pose_publisher.py` | Reads the robot's own position directly from the VICON PC and gives it to the controller.                                                              | Onboard Controller with pose source "onboard" |

Both are plain Python ROS 2 nodes (`rclpy`). They need no build step: copy them
over and run them with `python3`.

## Where does the robot get its position?

The controller needs to know where the robot is. Pick one of these in Henosync with
the device's **Onboard Controller Pose Source** setting:

- **Relayed by Henosync** (default). Henosync reads VICON on the laptop and forwards
  the position to the robot over rosbridge. Simple, but if the link between Henosync
  and the robot drops, the robot loses its position and **stops** (after 1.5 s).
- **Robot reads VICON itself**. `vicon_pose_publisher.py` on the robot connects to
  the VICON PC directly, like an onboard GPS. If the link to Henosync drops, the robot
  **keeps driving its path**. When the link comes back, Henosync reconnects
  automatically and picks up how far the robot got.

Either way, Henosync also keeps reading VICON itself, so the map and the recorded
trail stay live during a dropout.

## One-time setup

All steps can be done over SSH from your laptop.

### 1. Copy the scripts to the robot

From the Henosync repo folder **on your laptop** (not inside the SSH session):

```bash
scp tools/robot/henosync_controller.py tools/robot/vicon_pose_publisher.py <user>@<robot-ip>:~/henosync/
```

Re-copy them whenever you pull a Henosync update that changes `tools/robot/`.

### 2. VICON SDK on the robot (only for "Robot reads VICON itself")

The robot needs its own copy of the Vicon DataStream SDK, the **Linux** build (the
Windows copy on your laptop won't work), plus network access to the VICON PC.

```bash
# On the robot — the VICON PC must be reachable on port 801
nc -zv <vicon-pc-ip> 801
```

Download the DataStream SDK from Vicon, copy its Linux 64-bit Python package to
the robot with `scp -r`, then on the robot:

```bash
cd <folder containing the SDK's setup.py / pyproject.toml>
python3 -m pip install --user .
python3 -c "from vicon_dssdk import ViconDataStream; print('ok')"
```

If the import complains about a missing `.so` library, add the SDK folder holding
the `.so` files to `LD_LIBRARY_PATH` in `~/.bashrc`.

### 3. Henosync device settings

Devices → Edit the robot:

- Positioning Source: **VICON**, with **VICON Object Name** exactly as in the VICON software
- Tick the **Onboard Controller** capability
- **Onboard Controller Pose Source**: Relayed by Henosync, or Robot reads VICON itself

## Running

Start these on the robot (one SSH terminal each) **before** running a mission.
`<ns>` is the robot's ROS 2 namespace, the same as the Henosync device config
(e.g. `j100_0364`); leave `--namespace` out if it has none.

**Rosbridge** (if not already started by the robot's own launch):

```bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

**Pose publisher** (only for "Robot reads VICON itself"):

```bash
python3 vicon_pose_publisher.py --vicon_host <vicon-pc-ip> --object <vicon object name> --namespace <ns>
```

**Controller**, with the pose source chosen in Henosync:

```bash
# Clearpath Jackal: Robot reads VICON itself
python3 henosync_controller.py --namespace <ns> --unstamped \
  --cmd_vel_topic /<ns>/platform/cmd_vel_unstamped \
  --pose_topic /<ns>/henosync/onboard_pose

# Clearpath Jackal: Relayed by Henosync (leave out --pose_topic)
python3 henosync_controller.py --namespace <ns> --unstamped \
  --cmd_vel_topic /<ns>/platform/cmd_vel_unstamped

# TurtleBot3 (ROS 2 Jazzy, TwistStamped on /<ns>/cmd_vel): relayed
python3 henosync_controller.py --namespace <ns>
```

Add `2>&1 | tee controller.log` to keep a log of every waypoint reached.

### Checking it works

```bash
ros2 topic hz /<ns>/henosync/onboard_pose     # pose publisher: ~50 Hz
ros2 topic echo /<ns>/henosync/progress       # controller: progress while a mission runs
```

The controller prints `New path …` when Henosync sends work and
`Reached waypoint N/M` as it goes.

## Troubleshooting

| Symptom                                                           | Cause                                                                                                                          |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Henosync step fails: "Onboard controller not responding"          | `henosync_controller.py` isn't running, or its `--namespace` doesn't match the device config.                                  |
| Controller logs "No pose for 1.5s — holding position"             | Nothing is publishing the pose topic. Check the pose publisher is running, or, in relay mode, that Henosync is connected.       |
| Robot drives to the wrong places                                  | Pose and waypoints are in different frames. Use the same VICON object name in `vicon_pose_publisher.py` and in Henosync.       |
| Robot doesn't move but the controller logs a new path             | Wrong `--cmd_vel_topic`, or missing/extra `--unstamped` for the robot's velocity message type.                                 |
| Pose publisher logs "VICON … unreachable"                         | The robot can't reach the VICON PC on port 801. Check it's on the VICON network.                                               |
