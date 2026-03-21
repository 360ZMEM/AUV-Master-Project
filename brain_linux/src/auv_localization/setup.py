from setuptools import setup

package_name = 'auv_localization'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='zmem063',
    maintainer_email='zmem063@todo.todo',
    description='ES-EKF localization node for AUV',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'auv_localization_node = auv_localization.auv_localization_node:main',
        ],
    },
)
