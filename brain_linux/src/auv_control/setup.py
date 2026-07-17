from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'auv_decision_ros'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools', 'py_trees'],
    zip_safe=True,
    maintainer='zmem063',
    maintainer_email='zmem063@todo.todo',
    description='ROS2 wrapper package for AUV decision core',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'decision_node = auv_decision_ros.decision_node:main',
            'mock_sensor_input = auv_decision_ros.mock_sensor_input:main',
            'cable_tracking_node = auv_decision_ros.cable_tracking_node:main',
            'cable_mission_autostart_node = auv_decision_ros.cable_mission_autostart_node:main',
            'decoupled_cable_sim_node = auv_decision_ros.decoupled_cable_sim_node:main',
            'sensor_supervisor_node = auv_decision_ros.sensor_supervisor_node:main',
            'magnetic_sensor_wrapper_node = auv_decision_ros.magnetic_sensor_wrapper_node:main',
            'forward_sonar_wrapper_node = auv_decision_ros.forward_sonar_wrapper_node:main',
        ],
    },
)
