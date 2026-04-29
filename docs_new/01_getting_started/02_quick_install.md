# 快速安装

本文档指导你在 5 分钟内完成开发环境配置。

## 系统要求

### 硬件要求
- CPU: 4 核心及以上
- 内存: 8GB 及以上（推荐 16GB）
- 硬盘: 20GB 可用空间

### 软件要求
- **操作系统**: Ubuntu 22.04 LTS
- **Python**: 3.10+（系统 Python `/usr/bin/python3`）
- **ROS2**: Humble Hawksbill
- **显卡**: 支持 OpenGL 4.5+（用于 HoloOcean）

## 安装步骤

### 1. 安装 ROS2 Humble

如果尚未安装 ROS2 Humble：

```bash
# 添加 ROS2 apt 仓库
sudo apt update && sudo apt install software-properties-common -y
sudo add-apt-repository universe -y
sudo apt update && sudo apt install curl -y
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# 安装 ROS2 Humble
sudo apt update
sudo apt install ros-humble-desktop -y

# 配置环境
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 2. 安装 Python 依赖

**重要提示**: 使用系统 Python，避免使用 conda 环境！

```bash
# 确认使用系统 Python
which python3  # 应该输出 /usr/bin/python3

# 安装必要的 Python 包
/usr/bin/python3 -m pip install --user \
    zenoh \
    pyyaml \
    py_trees \
    rclpy \
    geometry_msgs \
    sensor_msgs \
    std_msgs \
    nav_msgs
```

### 3. 克隆项目

```bash
# 克隆仓库（如果还没有）
cd ~
git clone <repository-url> AUV_Master_Project
cd AUV_Master_Project
```

### 4. 首次构建 ROS2 工作区

```bash
cd scripts
bash start_lin_brain.sh bootstrap
```

这个脚本会：
- 检查系统 Python 环境
- 自动禁用 conda 环境
- 构建 brain_linux ROS2 工作区
- 安装必要的依赖

### 5. 验证安装

```bash
# 检查 ROS2 环境
source /opt/ros/humble/setup.bash
ros2 --version  # 应该显示 ROS 2 版本

# 检查 Python 包
/usr/bin/python3 -c "import zenoh; print(zenoh.__version__)"
/usr/bin/python3 -c "import py_trees; print(py_trees.__version__)"

# 检查项目结构
ls brain_linux/src/
```

## 常见安装问题

### 问题 1: ModuleNotFoundError: No module named 'zenoh'

**原因**: 可能使用了 conda 环境或 pip 安装到了错误的 Python 环境。

**解决方法**:
```bash
# 确认退出 conda 环境
conda deactivate
conda deactivate

# 使用系统 Python 重新安装
/usr/bin/python3 -m pip install --user zenoh
```

### 问题 2: ROS2 命令找不到

**原因**: ROS2 环境未正确 source。

**解决方法**:
```bash
source /opt/ros/humble/setup.bash
source ~/AUV_Master_Project/brain_linux/install/setup.bash
```

### 问题 3: 构建失败

**原因**: 可能是 Python 版本或路径问题。

**解决方法**:
```bash
# 清理构建缓存
cd brain_linux
rm -rf build install log

# 重新构建
cd ~/AUV_Master_Project/scripts
bash start_lin_brain.sh bootstrap
```

## 环境变量配置（可选）

为了方便使用，可以添加以下内容到 `~/.bashrc`：

```bash
# ROS2 环境
source /opt/ros/humble/setup.bash

# AUV 项目环境
export AUV_PROJECT_ROOT=~/AUV_Master_Project
source $AUV_PROJECT_ROOT/brain_linux/install/setup.bash

# 确保使用系统 Python
alias python=/usr/bin/python3
alias pip='/usr/bin/python3 -m pip'
```

## 下一步

安装完成后，继续阅读：
- [第一次运行](03_first_run.md) - 启动第一个仿真

## 需要帮助？

如果遇到安装问题：
1. 查看 [常见问题](04_faq.md)
2. 检查系统日志
3. 在项目 issue 中搜索类似问题
