#!/bin/bash
# Install ROS 2 Humble and build the Go2 autonomy stack. Safe to re-run.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "run as the lima user, not root" >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y curl ca-certificates gnupg build-essential cmake git \
  python3-dev python3-pip python3-numpy python3-yaml python-is-python3 \
  libusb-1.0-0-dev libeigen3-dev libopencv-dev

if [ ! -f /usr/share/keyrings/ros-archive-keyring.gpg ]; then
  sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu jammy main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list >/dev/null
sudo apt-get update
sudo apt-get install -y \
  ros-humble-ros-base \
  ros-humble-rmw-cyclonedds-cpp \
  ros-humble-rosidl-generator-dds-idl \
  ros-humble-pcl-ros \
  ros-humble-pcl-conversions \
  ros-humble-perception-pcl \
  ros-humble-tf-transformations \
  ros-humble-tf2-ros \
  ros-humble-tf2-eigen \
  ros-humble-tf2-geometry-msgs \
  ros-humble-tf2-sensor-msgs \
  ros-humble-message-filters \
  ros-humble-cv-bridge \
  ros-humble-visualization-msgs \
  ros-humble-sensor-msgs-py \
  ros-humble-joy \
  python3-colcon-common-extensions
python3 -m pip install --user transforms3d pyyaml

sudo tee /etc/netplan/60-go2.yaml >/dev/null <<'EOF'
network:
  version: 2
  ethernets:
    lima1:
      dhcp4: false
      addresses: [192.168.123.100/24]
      optional: true
EOF
sudo chmod 600 /etc/netplan/60-go2.yaml
sudo netplan apply

mkdir -p "$HOME/Desktop" "$HOME/autonomy_stack_go2"
tar -C /Users/ares-pc/localrepo/grok-hackathon-pavia/robot/autonomy_stack_go2 \
  --exclude build --exclude install --exclude log --exclude .git \
  -cf - . | tar -C "$HOME/autonomy_stack_go2" -xf -
# shellcheck disable=SC1091
set +u
source /opt/ros/humble/setup.bash
set -u
cd "$HOME/autonomy_stack_go2"
export CMAKE_BUILD_PARALLEL_LEVEL=4
colcon build --parallel-workers 1 --cmake-args -DCMAKE_BUILD_TYPE=Release \
  --packages-up-to vehicle_simulator point_lio_unilidar local_planner \
  terrain_analysis terrain_analysis_ext far_planner calibrate_imu transform_sensors
echo PROVISION_OK
