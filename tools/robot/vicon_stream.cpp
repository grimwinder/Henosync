// vicon_stream.cpp — prints one VICON object's pose to stdout, one line per frame:
//   <x_m> <y_m> <yaw_rad>
// Vicon ships no Python wrapper for Linux, only the C++ SDK library, so
// vicon_pose_publisher.py runs this and publishes what it prints. Same values
// Henosync's vicon_manager uses: root segment global translation (mm → m) and
// the Z angle of the global Euler XYZ rotation. Occluded frames are skipped.
// Exits on connection loss; vicon_pose_publisher.py restarts it.
//
// Build on the robot (SDK's Linux64 folder copied to ~/vicon_sdk):
//   g++ -O2 -std=c++14 vicon_stream.cpp -I ~/vicon_sdk -L ~/vicon_sdk \
//       -lViconDataStreamSDK_CPP -Wl,-rpath,$HOME/vicon_sdk -o ~/vicon_stream
//
// Usage: vicon_stream <vicon-host[:port]> <object name>

#include "DataStreamClient.h"

#include <cstdio>
#include <string>

using namespace ViconDataStreamSDK::CPP;

int main(int argc, char** argv)
{
  if (argc != 3)
  {
    std::fprintf(stderr, "usage: %s <vicon-host[:port]> <object name>\n", argv[0]);
    return 2;
  }
  const std::string host = argv[1];
  const std::string object = argv[2];

  Client client;
  if (client.Connect(host).Result != Result::Success)
  {
    std::fprintf(stderr, "vicon_stream: cannot connect to %s\n", host.c_str());
    return 1;
  }
  client.EnableSegmentData();
  client.SetStreamMode(StreamMode::ClientPull);
  std::fprintf(stderr, "vicon_stream: connected to %s, object '%s'\n", host.c_str(), object.c_str());

  while (client.IsConnected().Connected)
  {
    if (client.GetFrame().Result != Result::Success)
      continue;

    const std::string segment = client.GetSubjectRootSegmentName(object).SegmentName;
    const Output_GetSegmentGlobalTranslation t = client.GetSegmentGlobalTranslation(object, segment);
    if (t.Result != Result::Success || t.Occluded)
      continue;
    const Output_GetSegmentGlobalRotationEulerXYZ r = client.GetSegmentGlobalRotationEulerXYZ(object, segment);
    const double yaw = r.Result == Result::Success ? r.Rotation[2] : 0.0;

    std::printf("%.6f %.6f %.6f\n", t.Translation[0] / 1000.0, t.Translation[1] / 1000.0, yaw);
    std::fflush(stdout);
  }

  std::fprintf(stderr, "vicon_stream: connection lost\n");
  return 1;
}
