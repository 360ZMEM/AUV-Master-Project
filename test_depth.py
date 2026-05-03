import sys
sys.path.insert(0, '/root/PythonVehicleSimulator/src')
from python_vehicle_simulator.vehicles.remus100 import remus100
from python_vehicle_simulator.lib import simulate
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 无头模式

# 创建remus100车辆，目标深度30m
vehicle = remus100('depthHeadingAutopilot', r_z=30, r_psi=0, r_rpm=1525, V_current=0, beta_current=0)

# 初始状态
eta = np.array([0, 0, 0, 0, 0, 0], float)  # [x,y,z,phi,theta,psi]
nu = np.array([0, 0, 0, 0, 0, 0], float)   # [u,v,w,p,q,r]

sampleTime = 0.02
N = 5000  # 100秒仿真

# 手动仿真循环
depth_history = []
for i in range(N):
    t = i * sampleTime
    u_control = vehicle.depthHeadingAutopilot(eta, nu, sampleTime)
    nu, u_actual = vehicle.dynamics(eta, nu, vehicle.u_actual, u_control, sampleTime)
    # 运动学 (Euler)
    eta_dot = np.array([
        nu[0]*np.cos(eta[5])*np.cos(eta[4]),
        nu[0]*np.sin(eta[5])*np.cos(eta[4]),
        -nu[0]*np.sin(eta[4]),
        nu[3] + nu[4]*np.sin(eta[3])*np.tan(eta[4]) + nu[5]*np.cos(eta[3])*np.tan(eta[4]),
        nu[4]*np.cos(eta[3]) - nu[5]*np.sin(eta[3]),
        nu[4]*np.sin(eta[3])/np.cos(eta[4]) + nu[5]*np.cos(eta[3])/np.cos(eta[4])
    ])
    eta += sampleTime * eta_dot
    vehicle.u_actual = u_actual
    depth_history.append(eta[2])

depth_history = np.array(depth_history)
print(f"初始深度: {depth_history[0]:.2f} m")
print(f"最终深度: {depth_history[-1]:.2f} m")
print(f"最大深度: {depth_history.max():.2f} m")
print(f"目标深度: 30 m")
print(f"50秒时深度: {depth_history[2500]:.2f} m")
