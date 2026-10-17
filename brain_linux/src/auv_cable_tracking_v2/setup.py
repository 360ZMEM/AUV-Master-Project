from glob import glob
import os

from setuptools import find_packages, setup


package_name = "auv_cable_tracking_v2"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="zmem063",
    maintainer_email="zmem063@todo.todo",
    description="Independent ROS2 adapter for AUV magnetic cable tracking v2",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "cable_tracking_v2_node = auv_cable_tracking_v2.cable_tracking_v2_node:main",
            "inspection_controller_node = auv_cable_tracking_v2.inspection_controller_node:main",
            "inspection_bridge_node = auv_cable_tracking_v2.inspection_bridge_node:main",
            "inspection_setpoint_supervisor_node = auv_cable_tracking_v2.inspection_setpoint_supervisor_node:main",
            "imu_sidecar_node = auv_cable_tracking_v2.imu_sidecar_node:main",
        ],
    },
)
