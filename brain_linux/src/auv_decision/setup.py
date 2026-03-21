from setuptools import find_packages, setup

package_name = 'auv_decision_core'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'py_trees'],
    zip_safe=True,
    maintainer='zmem063',
    maintainer_email='zmem063@todo.todo',
    description='Pure-Python AUV behavior tree decision core',
    license='Apache-2.0',
    tests_require=['pytest'],
)
