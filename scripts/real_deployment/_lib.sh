#!/usr/bin/env bash
# Common library for scripts/real_deployment/* (五阶段实物部署 SOP)。
# Source with:  source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
#
# Provides:
#   require_target            parse --target {mock,vxsim,real} & --dry-run
#   require_real_confirm      enforce --i-have-physical-auv when target=real
#   start_log_receiver_bg     bg log_receiver.py -> RD_RUN_DIR/vxworks.log
#   start_mock_amd_bg         bg sim_holoocean main + protocol_udp (mock target)
#   stop_bg_pids              cleanup any pid recorded via track_bg_pid
#   assert_prev_stage_done    soft-warn if previous stage flag is missing
#   mark_stage_passed         touch RD_RUN_DIR/passed.flag
#
# All functions are prefix-namespaced as `rd_*` for grep-ability;
# legacy short names are wrappers for backward-friendly call sites.

set -euo pipefail

RD_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RD_SCRIPTS_DIR="$(cd "$RD_LIB_DIR/.." && pwd)"
RD_ROOT_DIR="$(cd "$RD_SCRIPTS_DIR/.." && pwd)"

RD_TARGET="${RD_TARGET:-mock}"
RD_DRY_RUN="${RD_DRY_RUN:-false}"
RD_HAVE_PHYSICAL="${RD_HAVE_PHYSICAL:-false}"
RD_DURATION_S="${RD_DURATION_S:-}"
RD_PASSTHROUGH=()
RD_BG_PIDS=()

rd_log() {
  printf '[real_deployment] %s\n' "$*"
}

rd_warn() {
  printf '[real_deployment][WARN] %s\n' "$*" >&2
}

rd_die() {
  printf '[real_deployment][FATAL] %s\n' "$*" >&2
  exit 1
}

rd_require_target() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --target)
        RD_TARGET="${2:?missing value for --target}"; shift 2 ;;
      --dry-run)
        RD_DRY_RUN=true; shift ;;
      --i-have-physical-auv)
        RD_HAVE_PHYSICAL=true; shift ;;
      --duration)
        RD_DURATION_S="${2:?missing value for --duration}"; shift 2 ;;
      --)
        shift; RD_PASSTHROUGH+=("$@"); break ;;
      *)
        RD_PASSTHROUGH+=("$1"); shift ;;
    esac
  done
  case "$RD_TARGET" in
    mock|vxsim|real) ;;
    *) rd_die "--target must be one of {mock,vxsim,real}, got '$RD_TARGET'" ;;
  esac
}

rd_require_real_confirm() {
  if [[ "$RD_TARGET" == "real" && "$RD_HAVE_PHYSICAL" != "true" ]]; then
    rd_die "--target real requires explicit --i-have-physical-auv (safety guard)."
  fi
}

rd_init_run_dir() {
  local stage_id="${1:-stage}"
  local ts; ts="$(date +%Y%m%d_%H%M%S)"
  local brain_params_file; brain_params_file="$(rd_brain_params_file)"
  RD_RUN_ID="${ts}_${stage_id}_${RD_TARGET}"
  RD_RUN_DIR="${RD_ROOT_DIR}/log/real_deployment/${RD_RUN_ID}"
  mkdir -p "$RD_RUN_DIR"
  {
    echo "run_id=$RD_RUN_ID"
    echo "stage=$stage_id"
    echo "target=$RD_TARGET"
    echo "dry_run=$RD_DRY_RUN"
    echo "duration_s=$RD_DURATION_S"
    echo "brain_params_file=$brain_params_file"
    echo "started_at=$(date --iso-8601=seconds)"
    echo "git_head=$(cd "$RD_ROOT_DIR" && git rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "passthrough=${RD_PASSTHROUGH[*]:-}"
  } > "$RD_RUN_DIR/metadata.txt"
  rd_log "run_dir: $RD_RUN_DIR"
  export RD_RUN_ID RD_RUN_DIR
}

rd_brain_params_file() {
  local override="${RD_BRAIN_PARAMS_FILE:-${AUV_RD_BRAIN_PARAMS_FILE:-}}"
  local default_file="${RD_ROOT_DIR}/brain_linux/config/params.protocol_udp_arbiter.${RD_TARGET}.yaml"
  local fallback_file="${RD_ROOT_DIR}/brain_linux/config/params.protocol_udp_arbiter.yaml"
  local selected

  if [[ -n "$override" ]]; then
    selected="$override"
  elif [[ -f "$default_file" ]]; then
    selected="$default_file"
  else
    selected="$fallback_file"
  fi

  [[ -f "$selected" ]] || rd_die "brain params file not found: $selected"
  printf '%s\n' "$selected"
}

rd_track_bg_pid() {
  RD_BG_PIDS+=("$1")
}

rd_stop_bg_pids() {
  local pid
  for pid in "${RD_BG_PIDS[@]:-}"; do
    [[ -z "$pid" ]] && continue
    kill -INT "$pid" >/dev/null 2>&1 || true
  done
  sleep 1 || true
  for pid in "${RD_BG_PIDS[@]:-}"; do
    [[ -z "$pid" ]] && continue
    kill -TERM "$pid" >/dev/null 2>&1 || true
  done
}

rd_start_log_receiver_bg() {
  local out="${RD_RUN_DIR}/vxworks.log"
  rd_log "starting log_receiver.py -> $out"
  if [[ "$RD_DRY_RUN" == "true" ]]; then
    rd_log "  [dry-run] python3 ${RD_SCRIPTS_DIR}/log_receiver.py --save $out"
    return 0
  fi
  python3 "${RD_SCRIPTS_DIR}/log_receiver.py" --save "$out" \
      > "${RD_RUN_DIR}/log_receiver.stdout" \
      2> "${RD_RUN_DIR}/log_receiver.stderr" &
  rd_track_bg_pid "$!"
}

rd_start_mock_amd_bg() {
  if [[ "$RD_TARGET" != "mock" ]]; then
    return 0
  fi
  rd_log "starting mock AMD (sim_holoocean main, backend=pvs, bridge=protocol_udp)"
  if [[ "$RD_DRY_RUN" == "true" ]]; then
    rd_log "  [dry-run] python3 ${RD_ROOT_DIR}/sim_holoocean/apps/main.py --backend pvs --bridge protocol_udp"
    return 0
  fi
  ( cd "$RD_ROOT_DIR" \
    && python3 sim_holoocean/apps/main.py --backend pvs --bridge protocol_udp \
        > "${RD_RUN_DIR}/mock_amd.stdout" \
        2> "${RD_RUN_DIR}/mock_amd.stderr" ) &
  rd_track_bg_pid "$!"
}

rd_assert_prev_stage_done() {
  local prev="$1"
  local glob_pattern="${RD_ROOT_DIR}/log/real_deployment/*_${prev}_*/passed.flag"
  if compgen -G "$glob_pattern" > /dev/null; then
    rd_log "found previous '$prev' passed flag (proceed)."
  else
    rd_warn "no previous '$prev' passed flag found under log/real_deployment/. Continuing (soft warning)."
  fi
}

rd_mark_stage_passed() {
  date --iso-8601=seconds > "${RD_RUN_DIR}/passed.flag"
  rd_log "marked stage passed: ${RD_RUN_DIR}/passed.flag"
}

rd_install_cleanup_trap() {
  trap 'rd_stop_bg_pids' EXIT INT TERM
}

rd_summary_banner() {
  local stage="$1"
  cat <<EOF
==================================================================
 real_deployment / stage = ${stage}
   target     : ${RD_TARGET}
   dry-run    : ${RD_DRY_RUN}
   physical   : ${RD_HAVE_PHYSICAL}
   run_dir    : ${RD_RUN_DIR:-<not yet initialized>}
==================================================================
EOF
}
