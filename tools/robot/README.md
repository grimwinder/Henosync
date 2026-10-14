# Robot-side scripts

Henosync runs on your laptop and talks to each robot over **rosbridge**. For most
features that's all you need: no Henosync code runs on the robot.

The **Onboard Controller** capability is the exception. With it, the robot drives
itself to the waypoints Henosync sends, so these scripts must be copied to the
robot's computer and run there:

| Script                   | What it does                                                                                                                                           | Needed for                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------- |
| `henosync_controller.py` | Receives waypoints (or a whole path) from Henosync and drives the robot to them with a proportional controller. Reports progress back to Henosync. | Onboard Controller capability (any mode)      |
| `vicon_pose_publisher.py` | Publishes the robot's own VICON position as a ROS topic for the controller (runs `vicon_stream` to read it).                                           | Onboard Controller with pose source "onboard" |
| `vicon_stream.cpp`       | Small C++ program that reads one object's pose from the VICON PC with Vicon's SDK. Compiled on the robot.                                               | Onboard Controller with pose source "onboard" |

The two `.py` scripts are plain Python ROS 2 nodes (`rclpy`): copy them over and
run them with `python3`. `vicon_stream.cpp` is compiled once on the robot, because
Vicon ships no Python SDK for Linux, only a C++ library.

## Where does the robot get its position?

The controller needs to know where the robot is. Pick one of these in Henosync with
the device's **Onboard Controller Pose Source** setting:

- **Relayed by Henosync** (default). Henosync reads VICON on the laptop and forwards
  the position to the robot over rosbridge. Simple, but if the link between Henosync
  and the robot drops, the robot loses its position and **stops** (after 1.5 s).
- **Robot reads VICON itself**. The robot connects to the VICON PC directly, like an
  onboard GPS. If the link to Henosync drops, the robot **keeps driving its path**.
  When the link comes back, Henosync reconnects automatically and picks up how far
  the robot got.

In "Robot reads VICON itself" mode, the position never goes through Henosync or
rosbridge:

```
VICON PC ──(Vicon DataStream, port 801 — not ROS)──► robot:
    vicon_stream ──(text pipe)──► vicon_pose_publisher.py
        ──(ROS topic /<ns>/henosync/onboard_pose, local to the robot)──► henosync_controller.py
```

Either way, Henosync also keeps reading VICON itself, so the map and the recorded
trail stay live during a dropout.

## One-time setup

All steps can be done over SSH from your laptop.

### 1. Copy the scripts to the robot

Run `scp` **on your laptop** (a laptop terminal, not inside the SSH session), from
the Henosync repo folder. Replace `<user>@<robot-ip>` with the robot's login, e.g.
`administrator@192.168.11.39`. On Windows PowerShell, type `cd` and `scp` as
separate commands, and don't leave the `<` `>` in: PowerShell treats `<` as a
special character.

```bash
cd <path to your Henosync repo>
scp tools/robot/henosync_controller.py tools/robot/vicon_pose_publisher.py tools/robot/vicon_stream.cpp <user>@<robot-ip>:~/
```

The commands below assume the files are in the robot's home folder (`~`).
Re-copy them whenever you pull a Henosync update that changes `tools/robot/`.

### 2. VICON on the robot (only for "Robot reads VICON itself")

**Check the robot can reach the VICON PC** (on the robot). It must say "succeeded":

```bash
nc -zv <vicon-pc-ip> 801
```

**Pick a Vicon SDK version the robot's Linux can load.** Vicon's Linux library is
pre-built, and newer releases need a newer C++ runtime than older Ubuntu has:

| Robot OS                     | Vicon DataStream SDK |
| ---------------------------- | -------------------- |
| Ubuntu 22.04 (ROS 2 Humble), e.g. the Clearpath Jackal | **1.11** (tested). 1.13 fails: it needs `GLIBCXX_3.4.32`, 22.04 has up to 3.4.30 |
| Ubuntu 24.04 (ROS 2 Jazzy)   | 1.13 should work     |

To check what a robot supports: `strings /usr/lib/x86_64-linux-gnu/libstdc++.so.6 | grep GLIBCXX_3.4.3`

Download that version from Vicon's DataStream SDK page (older versions are listed
there too), unzip it on your laptop and copy its `Linux64` folder to the robot as
`~/vicon_sdk` (laptop terminal):

```bash
scp -r "<unzipped SDK>/Linux64" <user>@<robot-ip>:~/vicon_sdk
```

**Build `vicon_stream`** (on the robot). No output means it worked:

```bash
g++ -O2 -std=c++14 ~/vicon_stream.cpp -I ~/vicon_sdk -L ~/vicon_sdk \
    -lViconDataStreamSDK_CPP -Wl,-rpath,$HOME/vicon_sdk -o ~/vicon_stream
```

**Test it** (on the robot). Use the robot's object name exactly as in the VICON
software (case-sensitive):

```bash
~/vicon_stream <vicon-pc-ip> <vicon object name>
```

It prints `vicon_stream: connected …`, then one line per VICON frame: `x_m y_m
heading_rad`. Push and rotate the robot to check the numbers change and match the
robot's position on Henosync's VICON map. Press Ctrl+C to stop. You only run it by
hand to test: `vicon_pose_publisher.py` starts it automatically.

### 3. Henosync device settings

Devices → Edit the robot:

- Positioning Source: **VICON**, with **VICON Object Name** exactly as in the VICON software
- Tick the **Onboard Controller** capability
- **Onboard Controller Pose Source**: Relayed by Henosync, or Robot reads VICON itself

## Running

Start these on the robot (one SSH terminal each) **before** running a mission.
`<ns>` is the robot's ROS 2 namespace, the same as the Henosync device config
(e.g. `j100_0364`); leave `--namespace` out if it has none. To find it:
`ros2 topic list | grep cmd_vel`, where the namespace is the part between the
first two slashes.

**Rosbridge** (if not already started by the robot's own launch):

```bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

**Pose publisher** (only for "Robot reads VICON itself"):

```bash
python3 ~/vicon_pose_publisher.py --vicon_host <vicon-pc-ip> --object <vicon object name> --namespace <ns>
```

It runs `~/vicon_stream` (override with `--stream_bin`) and restarts it if the
VICON connection drops.

**Controller**, with the pose source chosen in Henosync:

```bash
# Clearpath Jackal: Robot reads VICON itself
python3 ~/henosync_controller.py --namespace <ns> --unstamped \
  --cmd_vel_topic /<ns>/platform/cmd_vel_unstamped \
  --pose_topic /<ns>/henosync/onboard_pose

# Clearpath Jackal: Relayed by Henosync (leave out --pose_topic)
python3 ~/henosync_controller.py --namespace <ns> --unstamped \
  --cmd_vel_topic /<ns>/platform/cmd_vel_unstamped

# TurtleBot3 (ROS 2 Jazzy, TwistStamped on /<ns>/cmd_vel): relayed
python3 ~/henosync_controller.py --namespace <ns>
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
| Pose publisher logs "Cannot run …/vicon_stream"                   | `vicon_stream` isn't built, or isn't in the home folder. Build it (step 2) or pass `--stream_bin`.                             |
| `g++` says "vicon_stream.cpp: No such file or directory"          | `vicon_stream.cpp` wasn't copied to the robot. Re-run the `scp` from step 1.                                                    |
| `vicon_stream` errors with `` `GLIBCXX_3.4.xx' not found ``      | The Vicon SDK version is too new for the robot's Ubuntu. Use the version from the table in step 2.                              |
| `vicon_stream` connects but prints no lines                       | Wrong object name (it's case-sensitive), or the object is occluded / not tracked in the VICON software.                       |
