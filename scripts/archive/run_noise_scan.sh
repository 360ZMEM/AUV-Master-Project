#!/bin/bash
set -e
cd /home/auv_user/auv_ws/AUV-Master-Project
BAG=/auv_data/bags/20260609_090300/rosbag/rosbag_0.mcap
OUT=/home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2_noise_scan
rm -rf $OUT && mkdir -p $OUT

cp brain_linux/config/params.yaml $OUT/params_default.yaml
cp brain_linux/config/params.yaml $OUT/params_lo.yaml
sed -i 's/sigma_dvl: 0.03/sigma_dvl: 0.005/' $OUT/params_lo.yaml
cp brain_linux/config/params.yaml $OUT/params_match.yaml
sed -i 's/sigma_dvl: 0.03/sigma_dvl: 0.02/' $OUT/params_match.yaml

{
  for variant in default match lo; do
    echo "=== sigma_dvl variant = $variant ==="
    python3 tools/offline_ekf_benchmark.py \
      --input $BAG --output-dir $OUT/$variant \
      --ekf-config $OUT/params_$variant.yaml \
      --dr-mode dvl_world --skip-assertions 2>&1 \
      | grep -E 'sigma_dvl|raw_dr|std_ekf|es_ekf' | head -20
    echo
  done
} > $OUT/summary.txt 2>&1
echo done > $OUT/done
