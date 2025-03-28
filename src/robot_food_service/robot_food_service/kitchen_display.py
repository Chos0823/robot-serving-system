import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSReliabilityPolicy, QoSDurabilityPolicy
from order_management_interfaces.msg import OrderDetails
from order_management_interfaces.msg import RobotControl
from order_management_interfaces.srv import OrderValidation
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QGridLayout, QFrame
from PyQt5.QtCore import QTimer
import sqlite3

class KitchenDisplayNode(Node):
    def __init__(self):
        super().__init__('kitchen_display_node')
        self.current_request = None
        self.orders = {}

        # SQLite 데이터베이스 연결
        self.db_connection = sqlite3.connect('kitchen_orders.db')
        self.db_cursor = self.db_connection.cursor()

        # 주문 정보 테이블 생성
        self.create_orders_table()

        # PyQt5로 GUI 생성
        self.app = QApplication([])
        self.window = QWidget()
        self.window.setWindowTitle('주방 화면')
        self.window.resize(800, 800)

        # UI 구성
        self.layout = QVBoxLayout()

        # 3x3 그리드 레이아웃 설정
        self.grid_layout = QGridLayout()
        self.layout.addLayout(self.grid_layout)

        # 테이블에 대한 주문 정보 표시 및 리셋 버튼 추가
        self.table_frames = {}
        self.reset_buttons = {}
        for i in range(1, 10):
            frame = QFrame()
            frame.setFrameShape(QFrame.StyledPanel)
            frame.setLineWidth(2)
            frame.setStyleSheet("background-color: lightgray; padding: 10px;")
            frame.setFixedSize(230, 280)

            label = QLabel(f"테이블 {i}\n없음")
            label.setWordWrap(True)

            reset_button = QPushButton(f"결제하기")
            reset_button.clicked.connect(lambda _, table=i: self.reset_table(table))

            frame_layout = QVBoxLayout(frame)
            frame_layout.addWidget(label)
            frame_layout.addWidget(reset_button)

            self.table_frames[i] = label
            self.reset_buttons[i] = reset_button

            row = (i - 1) // 3
            col = (i - 1) % 3
            self.grid_layout.addWidget(frame, row, col)

        # 주문 내역 표시
        self.order_details_label = QLabel("주문 내역이 없습니다.")
        self.layout.addWidget(self.order_details_label)

        # 버튼 생성
        self.approve_button = QPushButton("주문 승인")
        self.reject_button = QPushButton("주문 거부")
        self.layout.addWidget(self.approve_button)
        self.layout.addWidget(self.reject_button)

        self.robot_serve_button = QPushButton("로봇 서빙")
        self.layout.addWidget(self.robot_serve_button)

        # 버튼 클릭 이벤트 연결
        self.approve_button.clicked.connect(self.approve_order)
        self.reject_button.clicked.connect(self.reject_order)
        self.robot_serve_button.clicked.connect(self.send_robot_control_message)

        # UI 설정
        self.window.setLayout(self.layout)
        self.window.show()

        # 주문 정보 수신 토픽 구독
        qos_profile = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE
        )
        self.order_subscriber = self.create_subscription(
            OrderDetails,
            'order_topic',
            self.handle_order_message,
            qos_profile
        )
        self.robot_control_publisher = self.create_publisher(RobotControl, 'robot_topic', qos_profile)
        self.get_logger().info(f"이동 정보 전송완료")

        self.order_validation_service = self.create_service(
            OrderValidation,
            'order_validation',
            self.handle_order_validation
        )
        self.get_logger().info("주문 검증 서비스가 생성되었습니다.")

        # PyQt5와 ROS2 이벤트 루프 통합
        self.timer = QTimer()
        self.timer.timeout.connect(self.spin_once)
        self.timer.start(100)

        self.app.exec_()

    def spin_once(self):
        rclpy.spin_once(self, timeout_sec=0.1)

    def create_orders_table(self):
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_number TEXT,
            menu_item TEXT,
            quantity INTEGER,
            total_price INTEGER
        )
        '''
        self.db_cursor.execute(create_table_query)
        self.db_connection.commit()

    def save_order_to_db(self, order_msg):
        table_number = order_msg.table_number
        total_price = order_msg.total_price

        menu_items = order_msg.menu_items
        quantities = order_msg.quantities

        for menu_item, quantity in zip(menu_items, quantities):
            insert_order_query = '''
            INSERT INTO orders (table_number, menu_item, quantity, total_price)
            VALUES (?, ?, ?, ?)
            '''
            self.db_cursor.execute(insert_order_query, (
                table_number,
                menu_item.strip(),
                quantity,
                total_price
            ))
        self.db_connection.commit()
        self.get_logger().info(f"주문이 데이터베이스에 저장되었습니다: {table_number}, {menu_items}, {quantities}")

    def handle_order_message(self, msg):
        order_info = (
            f"메뉴: {', '.join(msg.menu_items)}\n"
            f"수량: {', '.join(map(str, msg.quantities))}개\n"
            f"총 금액: {msg.total_price}원"
        )

        self.order_details_label.setText(order_info)
        self.save_order_to_db(msg)
        self.current_request = msg

    def approve_order(self):
        if self.current_request:
            self.get_logger().info(f"주문 승인 처리 완료: {self.current_request}")
            table_number = int(self.current_request.table_number)

            if table_number in self.table_frames:
                order_info = (
                    f"메뉴: {', '.join(self.current_request.menu_items)}\n"
                    f"수량: {', '.join(map(str, self.current_request.quantities))}개\n"
                    f"총 금액: {self.current_request.total_price}원"
                )
                self.table_frames[table_number].setText(f"테이블 {table_number}\n{order_info}")

            self.send_robot_control_message()
            self.current_request = None
            self.order_details_label.setText("주문 내역이 없습니다.")
        else:
            self.get_logger().warn("처리할 주문 요청이 없습니다.")
            self.order_details_label.setText("처리할 주문 요청이 없습니다.")

    def reject_order(self):
        if self.current_request:
            self.get_logger().info(f"주문 거부 처리 완료: {self.current_request}")
            self.order_details_label.setText("주문이 거부되었습니다.")
            self.current_request = None
        else:
            self.get_logger().warn("처리할 주문 요청이 없습니다.")
            self.order_details_label.setText("처리할 주문 요청이 없습니다.")

    def reset_table(self, table_number):
        if table_number in self.table_frames:
            self.table_frames[table_number].setText(f"테이블 {table_number}\n없음")
            self.get_logger().info(f"테이블 {table_number} 초기화 완료.")

    def send_robot_control_message(self):
        if not self.current_request:
            self.get_logger().warn("로봇 서빙 메시지를 보낼 주문이 없습니다.")
            return

        robot_control_msg = RobotControl()
        try:
            # table_number를 RobotControl 메시지의 order_id로 설정
            robot_control_msg.order_id = int(self.current_request.table_number)
            self.robot_control_publisher.publish(robot_control_msg)
            self.get_logger().info(f"로봇 서빙 메시지 퍼블리시: 테이블 {self.current_request.table_number}")
        except ValueError:
            self.get_logger().warn(f"유효하지 않은 테이블 번호: {self.current_request.table_number}")


    def handle_order_validation(self, request, response):
        self.get_logger().info(f"주문 검증 요청 수신: 테이블 번호 {request.order_details.table_number}")
        if self.current_request:
            response.is_valid = True
            response.message = "주문이 승인되었습니다."
        else:
            response.is_valid = False
            response.message = "주문이 거부되었습니다."

        return response

def main(args=None):
    rclpy.init(args=args)
    node = KitchenDisplayNode()
    rclpy.shutdown()
