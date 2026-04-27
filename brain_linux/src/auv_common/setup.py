from pathlib import Path

from setuptools import setup

package_name = 'auv_common'
workspace_common = Path(__file__).resolve().parents[3] / 'common'

setup(
    name=package_name,
    version='0.1.0',
    packages=['common'],
    package_dir={'common': str(workspace_common)},
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='zmem063',
    maintainer_email='zmem063@todo.todo',
    description='Shared Python contracts for the AUV ROS2 workspace',
    license='Apache-2.0',
    tests_require=['pytest'],
)