@echo off
setlocal

REM Start simulation side from unified AUV_Master_Project root.
REM Usage:
REM   start_win_sim.bat sim
REM   start_win_sim.bat bridge
REM   start_win_sim.bat both

set MODE=%~1
if "%MODE%"=="" set MODE=both

set ROOT_DIR=%~dp0..

echo [AUV] Root: %ROOT_DIR%
cd /d %ROOT_DIR%\sim_holoocean\apps || exit /b 1

if /i "%MODE%"=="bridge" goto START_BRIDGE
if /i "%MODE%"=="sim" goto START_SIM
if /i "%MODE%"=="both" goto START_BOTH

echo [AUV][ERROR] invalid mode: %MODE%
echo [AUV] valid modes: sim ^| bridge ^| both
exit /b 1

:START_SIM
echo [AUV] Starting main simulation...
python main.py --config ..\..\config\sim_params.yaml
if errorlevel 1 (
  echo [AUV][ERROR] main simulation failed.
  exit /b 1
)
goto END

:START_BRIDGE
echo [AUV] Starting Zenoh bridge...
python run_zenoh_bridge.py --config ..\..\config\bridge_params.yaml
if errorlevel 1 (
  echo [AUV][ERROR] bridge startup failed.
  exit /b 1
)
goto END

:START_BOTH
echo [AUV] Starting Zenoh bridge in new window...
start "AUV_Zenoh_Bridge" cmd /k python run_zenoh_bridge.py --config ..\..\config\bridge_params.yaml
echo [AUV] Starting main simulation in current window...
python main.py --config ..\..\config\sim_params.yaml
if errorlevel 1 (
  echo [AUV][ERROR] main simulation failed.
  exit /b 1
)

:END
echo [AUV] Completed.
endlocal
