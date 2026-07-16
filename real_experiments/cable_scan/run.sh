#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${SCRIPT_DIR}/config.yaml"
FANGKONG_ADC_DIR="$(awk -F': *' '/^fangkong_adc_dir:/ {print $2; exit}' "${CONFIG_PATH}")"
ADC_RECORD="$(awk -F': *' '/^adc_record:/ {print $2; exit}' "${CONFIG_PATH}")"

cd "${SCRIPT_DIR}/${FANGKONG_ADC_DIR}"

python3 scripts/joint_biot_savart_analysis.py --adc "${ADC_RECORD}"
