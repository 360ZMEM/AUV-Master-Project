#!/usr/bin/env bash
# Reproduce approved diagram repairs, formal exports, thesis PDF, and the full audit.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
export PYTHONPATH="$repo_root/.diagram-governance/pydeps${PYTHONPATH:+:$PYTHONPATH}"
export FONTCONFIG_FILE="$repo_root/config/diagram-governance/fonts.conf"

node tools/diagram-governance/cli.mjs doctor
python3 docs/thesis/figures/architecture/generate_architecture_diagrams.py >/dev/null
python3 AUV-Master-Mag/docs/figure/generate_drawio_method_figures.py >/dev/null

export_single_page() {
  local stem="$1"
  if [[ "$stem" == *"/auv_system_capability_map" ]]; then
    # Its feedback label extends the default PDF page box; --crop keeps one page.
    drawio --export --crop --format pdf --output "$stem.pdf" "$stem.drawio" >/dev/null
  else
    drawio --export --format pdf --output "$stem.pdf" "$stem.drawio" >/dev/null
  fi
  drawio --export --format png --output "$stem.png" "$stem.drawio" >/dev/null
  drawio --export --format svg --output "$stem.svg" "$stem.drawio" >/dev/null
  drawio --export --embed-diagram --format png --output "$stem.drawio.png" "$stem.drawio" >/dev/null
}

for stem in \
  AUV-Master-Mag/docs/figure/fig_mission_fsm \
  AUV-Master-Mag/docs/figure/fig_statemachine_hierarchy \
  AUV-Master-Mag/docs/figure/fig_arch_onion \
  docs/thesis/figures/architecture/auv_system_capability_map \
  docs/thesis/figures/architecture/auv_system_verification_deployment_ladder \
  docs/thesis/figures/architecture/auv_thesis_technical_route \
  docs/thesis/figures/architecture/auv_v2_uncertainty_highway; do
  export_single_page "$stem"
done
python3 docs/thesis/figures/architecture/export_five_layer_architecture.py
python3 docs/thesis/figures/architecture/sync_mag_architecture_copies.py >/dev/null
make auv-thesis
node tools/diagram-governance/cli.mjs run --all
