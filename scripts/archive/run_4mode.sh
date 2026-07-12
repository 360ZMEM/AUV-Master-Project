#!/bin/bash
set -e
cd /home/auv_user/auv_ws/AUV-Master-Project
BAG=/auv_data/bags/20260609_090300/rosbag/rosbag_0.mcap
OUT=/home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2
rm -rf $OUT && mkdir -p $OUT
{
  for mode in dvl_world dvl_body imu_only heading_only; do
    echo "=== DR mode = $mode ==="
    python3 tools/offline_ekf_benchmark.py \
      --input $BAG \
      --output-dir $OUT/$mode \
      --dr-mode $mode 2>&1 | grep -E 'raw_dr|std_ekf|es_ekf|Assertion'
    echo
  done
} > $OUT/summary.txt 2>&1
echo done
