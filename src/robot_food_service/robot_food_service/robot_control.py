import sys
import queue
import rclpy
import threading
from functools import partial
import sqlite3

from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QTextBrowser, QWidget
from PyQt5.QtCore import QRect

from rclpy.node import Node
from rclpy.action import ActionClient
from geometry_msgs.msg import PointStamped, Point, Quaternion
from nav2_msgs.action import NavigateToPose
from nav2_msgs.srv import SetInitialPose
from rclpy.action.client import GoalStatus

# 커스텀 메시지 임포트
from order_management_interfaces.msg import RobotControl  # 커스텀 메시지 import

class NODE(Node, QObject):
    signal = pyqtSignal(list)

    def __init__(self, node_name='gui_node'):
        Node.__init__(self, node_name)
        QObject.__init__(self)
        
        self.num = 9  # 테이블 수
        self.current_order_id = -1  # 추가된 부분: 현재 주문 ID
        self.init_pose = [0.0, 0.0, 0.0, 1.0]  # 초기 로봇 위치
        self.table_coords = [
            [3.109162110811999, 1.064675670588104], [3.153391448984137, -1.0491125084255173], [3.193308523192465, 2.0342932481312683],     
            [0.44415937076368955, 0.4999638724737042], [0.4398148607080405, -0.5713670076206864], [0.4608367135716978, 1.5926609706591535], 
            [1.9639341467418672, -1.1660702113994799], [1.983667568246241, 2.0623549505022147], [2.0777497362532062, 1.0475412036423666]
                        
        ]
        self.goal_poses = [[0.0, 0.0] for _ in range(self.num)]
        self.setting_poses = [False for _ in range(self.num)]

        self.queue = queue.Queue()
        self.timer = self.create_timer(0.1, self.process_queue)

        # 클릭된 지점 구독
        self.clicked_point_subscriber = self.create_subscription(
            PointStamped,
            "/clicked_point",
            self.clicked_point_callback,
            10
        )

        # 주문 번호에 따른 로봇 이동을 위한 서브스크라이버 추가
        self.robot_control_subscriber = self.create_subscription(
            RobotControl(),  
            'robot_control', 
            self.robot_control_callback, 
            10
        )
        
        # 서비스 클라이언트 초기화
        self.set_initial_pose_service_client = self.create_client(
            SetInitialPose, "/set_initial_pose"
        )
        
        # 네비게이션 액션 클라이언트 초기화
        self.navigate_to_pose_action_client = ActionClient(
            self, NavigateToPose, "navigate_to_pose"
        )
        
        while not self.set_initial_pose_service_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Service /set_initial_pose not available, waiting again...')
        self.set_initial_pose(*self.init_pose)

    def process_queue(self):
        while not self.queue.empty():
            cmd, val = self.queue.get()
            if cmd == 'navigate_to_pose_send_goal':
                self.navigate_to_pose_send_goal(val)

    def clicked_point_callback(self, msg):
        self.get_logger().info(f'Received point: x={msg.point.x}, y={msg.point.y}')
        for i in range(self.num):
            if self.setting_poses[i]:
                x = round(float(msg.point.x), 1)
                y = round(float(msg.point.y), 1)
                self.goal_poses[i][0] = x
                self.goal_poses[i][1] = y
                self.signal.emit(['set_label', i, f"x= {x:.1f}, y= {y:.1f}"])
                self.setting_poses[i] = False

    def set_initial_pose(self, x, y, z, w):
        req = SetInitialPose.Request()
        req.pose.header.frame_id = 'map'
        req.pose.pose.pose.position = Point(x=x, y=y, z=0.0)
        req.pose.pose.pose.orientation = Quaternion(x=0.0, y=0.0, z=z, w=w)
        req.pose.pose.covariance = [0.1, 0.0, 0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                     0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0,
                                     0.0, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.01]
        
        future = self.set_initial_pose_service_client.call_async(req)
        future.add_done_callback(lambda f: self.signal.emit([
            'append_textBrowser', '[INFO] Initial pose set successfully' if f.result() else '[WARN] Failed to set initial pose'
        ]))
        
    def navigate_to_pose_send_goal(self, i):
        if not self.navigate_to_pose_action_client.wait_for_server(timeout_sec=3.0):
            self.signal.emit(['append_textBrowser', '[WARN] Navigate action server is not available.'])
            return

        # 목표 위치를 확인
        x, y = self.goal_poses[i]
        
        # 초기 위치로 복귀할 경우 경고 메시지를 출력하지 않음
        if i != 0 and x == 0.0 and y == 0.0:
            self.signal.emit(['append_textBrowser', f'[WARN] 테이블 {i + 1}로의 이동 좌표가 설정되지 않았습니다.'])
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.frame_id = "map"
        goal_msg.pose.pose.position.x = x
        goal_msg.pose.pose.position.y = y
        goal_msg.pose.pose.orientation.w = 1.0

        self.send_goal_future = self.navigate_to_pose_action_client.send_goal_async(
            goal_msg, feedback_callback=self.navigate_to_pose_action_feedback
        )
        self.send_goal_future.add_done_callback(self.navigate_to_pose_action_goal)


    def navigate_to_pose_action_goal(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.signal.emit(['append_textBrowser', '[WARN] Action goal rejected.'])
            return

        self.signal.emit(['append_textBrowser', '[INFO] 로봇 수신 양호'])
        self.action_result_future = goal_handle.get_result_async()
        self.action_result_future.add_done_callback(self.navigate_to_pose_action_result)

    def navigate_to_pose_action_feedback(self, feedback_msg):
        pass

    def navigate_to_pose_action_result(self, future):
        result = future.result()
        if result.status == GoalStatus.STATUS_SUCCEEDED:
            self.signal.emit(['append_textBrowser', '[INFO] 로봇 이동 완료!'])
        else:
            self.signal.emit(['append_textBrowser', f'[WARN] Action failed with status: {result.status}'])

    def return_to_initial_position(self):
        self.goal_poses[0] = [0.0, 0.0]
        self.queue.put(['navigate_to_pose_send_goal', 0])

    def robot_control_callback(self, msg):
            # Open SQLite connection and fetch the most recent order
            try:
                conn = sqlite3.connect('kitchen_orders.db')  # Change to the correct path if needed
                cursor = conn.cursor()
                
                # Fetch the most recent row from the database based on order ID or timestamp
                cursor.execute("SELECT id, table_number FROM orders ORDER BY id DESC LIMIT 1")
                result = cursor.fetchone()

                if result is not None:
                    order_id, table_number = result  # Extract order_id and table_number from the result
                    self.current_order_id = order_id  # Set current order ID
                    table_number=int(table_number)
                    

                    # Process the table_number to get the corresponding position
                    if table_number >= 1 and table_number <= self.num:
                        table_position = self.table_coords[table_number]  # Adjust for 1-based index
                        self.get_logger().info(f"Moving to table {table_number} at position {table_position}")
                        
                        # 상태창에 테이블 번호와 이동 중 메시지 출력
                        self.signal.emit(['append_textBrowser', f"이동할 테이블 번호 : {table_number}"])
                        self.signal.emit(['append_textBrowser', "로봇 이동 중..."])

                        # 목표 위치로 로봇 이동
                        self.goal_poses[table_number - 1] = table_position
                        self.queue.put(['navigate_to_pose_send_goal', table_number - 1])
                    else:
                        self.get_logger().warn(f"Invalid table_number: {table_number}")
                else:
                    self.get_logger().warn("No orders found in the database.")
                    
                conn.close()

            except sqlite3.Error as e:
                self.get_logger().warn(f"SQLite error: {str(e)}")
            except Exception as e:
                self.get_logger().warn(f"Error in robot_control_callback: {str(e)}")

class GUI:
    def __init__(self, node):
        self.node = node
        self.node.signal.connect(self.process_signal)
        self.setup_ui()

    def setup_ui(self):
        self.num = self.node.num
        
        self.window = QMainWindow()
        self.window.setWindowTitle("Robot Controller")
        self.window.resize(300, 200 + 40 * self.num)
        self.central_widget = QWidget(self.window)
        self.window.setCentralWidget(self.central_widget)
        
        # "이동" 버튼을 하나만 추가
        self.move_button = QPushButton(self.central_widget)
        self.move_button.setText("이동")
        self.move_button.setGeometry(QRect(20, 20, 60, 30))
        self.move_button.clicked.connect(self.move_button_clicked)

        # 복귀 버튼 유지
        self.return_button = QPushButton(self.central_widget)
        self.return_button.setText("복귀")
        self.return_button.setGeometry(QRect(100, 20, 60, 30))
        self.return_button.clicked.connect(self.return_button_clicked)

        # 상태 창
        self.text_browser = QTextBrowser(self.central_widget)
        self.text_browser.setGeometry(QRect(20, 70, 260, 120))

    def process_signal(self, signal):
        cmd = signal[0]
        if cmd == 'append_textBrowser':
            self.text_browser.append(signal[1])

    def move_button_clicked(self):
        msg = RobotControl()
        

        self.node.robot_control_callback(msg)  # 로봇 제어 콜백 호출        
       

    def return_button_clicked(self):
        self.node.return_to_initial_position()
        self.text_browser.append("[INFO] 주방으로 되돌아가는중...")


def main():
    rclpy.init()
    node = NODE()
    ros_thread = threading.Thread(target=lambda: rclpy.spin(node), daemon=True)
    ros_thread.start()

    app = QApplication(sys.argv)
    gui = GUI(node)
    gui.window.show()

    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        sys.exit(0)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
