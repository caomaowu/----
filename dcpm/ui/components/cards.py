from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt
from qfluentwidgets import CardWidget
from dcpm.ui.theme.colors import COLORS

class ShadowCard(CardWidget):
    """带精致阴影的卡片基类"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setShadowEffect()
        
    def setShadowEffect(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 25))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
    def enterEvent(self, event):
        # 鼠标悬停时阴影加深并上移
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self.setShadowEffect()
        super().leaveEvent(event)

class StatCard(QWidget):
    """顶部统计卡片"""
    
    def __init__(self, title, value, subtitle, color, progress, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.title = title
        self.value = value
        self.subtitle = subtitle
        self.color = color
        self.progress = progress
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)
        
        # 标题
        title_label = QLabel(self.title)
        title_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 13px;")
        layout.addWidget(title_label)
        
        # 数值和进度
        value_layout = QHBoxLayout()
        
        # 大数字
        value_label = QLabel(str(self.value))
        value_font = QFont("Segoe UI", 32, QFont.Weight.Bold)
        value_label.setFont(value_font)
        value_label.setStyleSheet(f"color: {self.color};")
        value_layout.addWidget(value_label)
        
        value_layout.addStretch()
        
        # 副标题
        sub_label = QLabel(self.subtitle)
        sub_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        value_layout.addWidget(sub_label)
        
        layout.addLayout(value_layout)
        
        # 进度条
        progress_container = QWidget()
        progress_container.setFixedHeight(6)
        progress_container.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['border']};
                border-radius: 3px;
            }}
        """)
        
        progress_bar = QWidget(progress_container)
        progress_bar.setFixedHeight(6)
        progress_bar.setFixedWidth(int(max(0, min(1, self.progress)) * 200)) # 简单模拟宽度，实际应根据父容器计算
        progress_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {self.color};
                border-radius: 3px;
            }}
        """)
        
        layout.addWidget(progress_container)
        
        # 白色背景
        self.setStyleSheet(f"""
            StatCard {{
                background-color: {COLORS['card']};
                border-radius: 16px;
            }}
        """)

    def resizeEvent(self, event):
        # 简单的响应式进度条调整
        super().resizeEvent(event)
        # 实际项目中可能需要更复杂的布局来处理进度条宽度
