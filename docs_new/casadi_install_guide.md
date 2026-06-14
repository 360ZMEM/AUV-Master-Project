# CasADi 安装指引

## 环境信息

- 操作系统: Linux (ARM aarch64)
- Python: 3.10.12
- CasADi: 3.7.2

## 安装步骤

```bash
pip install casadi
```

## 验证安装

```bash
python3 -c "import casadi; print(casadi.__version__)"
```

预期输出: `3.7.2`

## 常见问题

### 1. pip 找不到 casadi 包

确保 pip 版本足够新:

```bash
pip install --upgrade pip
pip install casadi
```

### 2. 架构兼容性

CasADi 从 3.6+ 开始提供 `manylinux2014_aarch64` 预编译 wheel。如果你的 Python 版本是 3.8-3.11，直接 pip install 即可。

如果预编译 wheel 不可用，需要从源码编译:

```bash
sudo apt-get install -y build-essential cmake git
pip install --no-binary casadi casadi
```

### 3. IPOPT 求解器依赖

CasADi 内置 IPOPT 求解器（通过 `casadi.nlpsol`），无需单独安装。默认使用 `ipopt` 作为 MPC 求解后端。

### 4. 在 ROS2 环境中使用

确保在 ROS2 工作空间中 source 了正确的 Python 环境:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
python3 -c "import casadi; print('OK')"
```
