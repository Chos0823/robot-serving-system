from setuptools import find_packages, setup

package_name = 'robot_food_service'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='johyunsuk',
    maintainer_email='johyunsuk@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'order_table_node = robot_food_service.order_table:main', 
            'kitchen_display_node = robot_food_service.kitchen_display:main',
            'robot_control_node = robot_food_service.robot_control:main', 
        ],
    },
)
