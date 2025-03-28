from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QGridLayout, QPushButton, QLabel, QComboBox, QGroupBox
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap
import sys
import rclpy
from rclpy.node import Node
from order_management_interfaces.srv import OrderValidation
from order_management_interfaces.msg import OrderDetails
from order_management_interfaces.msg import RobotControl  # 로봇 제어 메시지 임포트
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSReliabilityPolicy
import time


class OrderTableNode(Node):
    def __init__(self):
        super().__init__('order_table_node')

        # 서비스 클라이언트 생성
        self.client = self.create_client(OrderValidation, 'order_validation')

        # PyQt5로 GUI 생성
        self.app = QApplication(sys.argv)
        self.window = QWidget()
        self.window.setWindowTitle('테이블 주문')

        # 메뉴 정보
        self.menu = {
            "라면": {"price": 5000, "image": "ramen.png"},
            "김밥": {"price": 4000, "image": "gimbap.png"},
            "돈까스": {"price": 10000, "image": "pig.png"},
            "우동": {"price": 8500, "image": "udong.png"},
            "카레": {"price": 9000, "image": "care.png"},
            "치킨카레": {"price": 10500, "image": "chickencare.png"}
        }
        self.image_path = "/home/johyunsuk/ros2_ws/src/robot_food_service/food_pictures"

        # UI 레이아웃 구성
        self.layout = QVBoxLayout()

        # 테이블 번호 선택
        self.table_label = QLabel("테이블 번호 선택 (1-9):")
        self.layout.addWidget(self.table_label)
        self.table_combo = QComboBox()
        self.table_combo.addItems([str(i) for i in range(1, 10)])
        self.layout.addWidget(self.table_combo)

        # 메뉴 선택 그룹
        self.menu_group = QGroupBox("메뉴")
        self.menu_layout = QGridLayout()  # GridLayout 사용

        self.menu_widgets = {}
        row, col = 0, 0
        for menu_item, data in self.menu.items():
            # 이미지 라벨
            image_label = QLabel()
            pixmap = QPixmap(f"{self.image_path}/{data['image']}")
            scaled_pixmap = pixmap.scaled(200, 150, Qt.KeepAspectRatio)  # 이미지 크기 통일
            image_label.setPixmap(scaled_pixmap)
            self.menu_layout.addWidget(image_label, row, col, 1, 3)  # 3칸 사용

            # 메뉴 이름 및 가격 라벨
            label = QLabel(f"{menu_item} - {data['price']}원")
            label.setAlignment(Qt.AlignCenter)  # 중앙 정렬
            self.menu_layout.addWidget(label, row + 1, col, 1, 3)

            # 수량 및 버튼
            quantity_label = QLabel("0")
            quantity_label.setAlignment(Qt.AlignCenter)

            minus_button = QPushButton("-")
            minus_button.setFixedWidth(40)  # 버튼 크기 조정
            minus_button.clicked.connect(lambda _, lbl=quantity_label, item=menu_item: self.update_quantity(lbl, item, -1))

            plus_button = QPushButton("+")
            plus_button.setFixedWidth(40)  # 버튼 크기 조정
            plus_button.clicked.connect(lambda _, lbl=quantity_label, item=menu_item: self.update_quantity(lbl, item, 1))

            # 버튼 및 수량 배치
            self.menu_layout.addWidget(minus_button, row + 2, col)
            self.menu_layout.addWidget(quantity_label, row + 2, col + 1)
            self.menu_layout.addWidget(plus_button, row + 2, col + 2)

            # 수량 라벨 저장
            self.menu_widgets[menu_item] = {"quantity_label": quantity_label, "quantity": 0}

            # 다음 칸으로 이동
            col += 3
            if col >= 6:  # 2열 기준으로 배치
                col = 0
                row += 3

        self.menu_group.setLayout(self.menu_layout)
        self.layout.addWidget(self.menu_group)

        # 총 금액과 주문 버튼
        self.total_label = QLabel("총 금액: 0원")
        self.layout.addWidget(self.total_label)

        self.order_button = QPushButton("주문하기")
        self.order_button.clicked.connect(self.place_order)
        self.layout.addWidget(self.order_button)

        self.status_label = QLabel("")
        self.layout.addWidget(self.status_label)

        # 메인 윈도우 설정
        self.window.setLayout(self.layout)
        self.window.show()

        self.timer = QTimer(self.window)
        self.timer.timeout.connect(self.spin_once)
        self.timer.start(100)

        self.app.exec_()

    def update_quantity(self, quantity_label, menu_item, change):
        current_quantity = self.menu_widgets[menu_item]["quantity"]
        new_quantity = max(0, current_quantity + change)  # 최소 0
        self.menu_widgets[menu_item]["quantity"] = new_quantity
        quantity_label.setText(str(new_quantity))
        self.update_total_price()

    def update_total_price(self):
        total_price = 0
        for menu_item, widgets in self.menu_widgets.items():
            total_price += self.menu[menu_item]["price"] * widgets["quantity"]
        self.total_label.setText(f"총 금액: {total_price}원")

    def place_order(self):
        table_number = int(self.table_combo.currentText())
        menu_items = []
        quantities = []
        total_price = 0.0

        for menu_item, widgets in self.menu_widgets.items():
            quantity = widgets["quantity"]
            if quantity > 0:
                menu_items.append(menu_item)
                quantities.append(quantity)
                total_price += self.menu[menu_item]["price"] * quantity

        if not menu_items:
            self.get_logger().warn("메뉴를 선택하지 않았습니다.")
            return

        order_msg = OrderDetails()
        order_msg.table_number = table_number
        order_msg.menu_items = menu_items
        order_msg.quantities = quantities
        order_msg.total_price = total_price

        self.send_order_to_kitchen(order_msg)
        self.status_label.setText("주문 처리 중...")
        self.check_order_validity(order_msg)

    def check_order_validity(self, order_msg):
        if not self.client.wait_for_service(timeout_sec=1.0):
            self.status_label.setText("주방 응답 없음")
            return

        request = OrderValidation.Request()
        request.order_details = order_msg
        future = self.client.call_async(request)
        future.add_done_callback(self.handle_order_response)

    def send_order_to_kitchen(self, order_msg):
        qos_profile = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=QoSReliabilityPolicy.RELIABLE
        )
        order_pub = self.create_publisher(OrderDetails, 'order_topic', qos_profile)
        order_pub.publish(order_msg)
        self.get_logger().info(f"주문 정보 전송: {order_msg}")

    def handle_order_response(self, future):
        try:
            response = future.result()
            if response.is_valid:
                self.status_label.setText("주문이 승인되었습니다.")
                self.approve_order(response)  # 주문이 승인되면 로봇 제어로 전달
            else:
                self.status_label.setText(f"주문이 거부되었습니다.")
        except Exception as e:
            self.status_label.setText("주문 처리 중...")
            time.sleep(10)
            self.status_label.setText("주문이 완료되었습니다.")

            



    def spin_once(self):
        rclpy.spin_once(self, timeout_sec=0.1)


def main(args=None):
    rclpy.init(args=args)
    node = OrderTableNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
