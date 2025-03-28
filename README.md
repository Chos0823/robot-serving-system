
# 🍽️ Robot Serving System

A ROS2-based autonomous robot serving system that simulates a smart restaurant environment using TurtleBot3.  
The system enables robot navigation, order taking, kitchen display updates, and automatic food delivery.

---

## 📁 Project Structure

```
Robot_Serving_System/
└── B5_Serving_System/
    ├── map.yaml / map.pgm          # Restaurant map for SLAM/Navigation
    ├── src/                        # Source code for ROS2 nodes
    ├── demo video.webm             # Demo video file
    ├── README.md
    └── b-5 Serving_System.pptx     # Project presentation
```

---

## 🚀 How to Run

1. **Launch the simulation environment**  
   ```bash
   ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py
   ```

2. **Launch navigation with a custom map**  
   > ⚠️ Replace the map path with your own full path  
   ```bash
   ros2 launch turtlebot3_navigation2 navigation2.launch.py map:=/home/your_name/map.yaml
   ```

3. **Run core service nodes**
   ```bash
   ros2 run robot_food_service order_table_node
   ros2 run robot_food_service kitchen_display_node
   ros2 run robot_food_service robot_control_node
   ```

---

## 💡 Features

- Autonomous navigation using ROS2 Navigation2
- Interactive order placement system
- Kitchen display integration
- Robot movement control for food delivery
