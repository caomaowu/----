from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
)
from qfluentwidgets import IconWidget, FluentIcon as FI

from dcpm.ui.theme.colors import COLORS

class SidebarWidget(QWidget):
    """精致的左侧导航 - 参考 main_v2.py"""
    
    navChanged = pyqtSignal(str) # "all", "fav", "month:2024-03", "filter:ongoing", etc.
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self.setStyleSheet(f"background-color: {COLORS['bg']}; border-right: 1px solid {COLORS['border']};")
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 28, 20, 28)
        layout.setSpacing(6)
        
        # Logo - 更精致
        logo_container = QWidget()
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        
        # Logo图标带渐变背景
        logo_icon = QWidget()
        logo_icon.setFixedSize(40, 40)
        logo_icon.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {COLORS['primary']},
                    stop:1 {COLORS['primary_light']});
                border-radius: 10px;
            }}
        """)
        logo_inner = QVBoxLayout(logo_icon)
        logo_inner.setContentsMargins(0, 0, 0, 0)
        icon = IconWidget(FI.HOME)
        icon.setFixedSize(20, 20)
        icon.setStyleSheet("color: white;")
        logo_inner.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        
        logo_layout.addWidget(logo_icon)
        logo_layout.addSpacing(12)
        
        logo_text = QLabel("压铸项目库")
        logo_font = QFont("Microsoft YaHei", 16, QFont.Weight.Bold)
        logo_text.setFont(logo_font)
        logo_text.setStyleSheet(f"color: {COLORS['text']};")
        logo_layout.addWidget(logo_text)
        logo_layout.addStretch()
        
        layout.addWidget(logo_container)
        layout.addSpacing(40)
        
        # 导航按钮组
        self.nav_group = []
        
        def create_nav_btn(text, data_key, checked=False):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(checked)
            btn.setFixedHeight(48)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding: 12px 16px;
                    border: none;
                    border-radius: 12px;
                    font-size: 14px;
                    color: {COLORS['text_muted']};
                    background: transparent;
                }}
                QPushButton:hover {{
                    background-color: #F8F9FA;
                    color: {COLORS['text']};
                }}
                QPushButton:checked {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #FFF3E0,
                        stop:1 white);
                    color: {COLORS['primary']};
                    font-weight: bold;
                }}
            """)
            btn.clicked.connect(lambda: self._on_nav_clicked(btn, data_key))
            self.nav_group.append(btn)
            return btn
        
        # 主导航
        layout.addWidget(create_nav_btn("📁   全部项目", "all", checked=True))
        layout.addWidget(create_nav_btn("⭐   置顶项目", "pinned"))
        
        layout.addSpacing(24)
        
        # 快速筛选
        filter_header = QLabel("⚡ 状态筛选")
        filter_header.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: bold; padding: 8px 16px;")
        layout.addWidget(filter_header)
        
        filters = [("进行中", "ongoing"), ("已交付", "delivered"), ("已归档", "archived")]
        for label, key in filters:
            layout.addWidget(create_nav_btn(f"    {label}", f"status:{key}"))
        
        layout.addSpacing(24)
        
        # 月份 (动态生成占位，实际应该从外部传入)
        month_header = QLabel("📅 最近月份")
        month_header.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: bold; padding: 8px 16px;")
        layout.addWidget(month_header)
        
        self.month_container = QVBoxLayout()
        self.month_container.setSpacing(4)
        layout.addLayout(self.month_container)
        
        layout.addStretch()
        
        # 用户区域
        user_card = QWidget()
        user_card.setFixedHeight(64)
        user_card.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['bg']};
                border-radius: 12px;
            }}
        """)
        user_layout = QHBoxLayout(user_card)
        user_layout.setContentsMargins(12, 8, 12, 8)
        
        # 头像
        avatar = QWidget()
        avatar.setFixedSize(40, 40)
        avatar.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {COLORS['primary_light']},
                    stop:1 {COLORS['primary']});
                border-radius: 20px;
            }}
        """)
        user_layout.addWidget(avatar)
        user_layout.addSpacing(10)
        
        # 用户信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        name_label = QLabel("管理员")
        name_label.setStyleSheet(f"color: {COLORS['text']}; font-weight: bold; font-size: 13px;")
        info_layout.addWidget(name_label)
        
        self.index_status = QLabel("索引正常")
        self.index_status.setStyleSheet(f"color: {COLORS['success']}; font-size: 11px;")
        info_layout.addWidget(self.index_status)
        
        user_layout.addLayout(info_layout)
        user_layout.addStretch()
        
        layout.addWidget(user_card)

    def _on_nav_clicked(self, sender: QPushButton, key: str):
        for btn in self.nav_group:
            btn.setChecked(btn == sender)
        self.navChanged.emit(key)

    def update_months(self, months: list[tuple[str, str, int]]):
        # months: [(display_name, key, count), ...]
        # 清除旧的月份按钮
        while self.month_container.count():
            item = self.month_container.takeAt(0)
            if item.widget():
                if item.widget() in self.nav_group:
                    self.nav_group.remove(item.widget())
                item.widget().deleteLater()
        
        for name, key, count in months[:5]: # 只显示前5个月
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            
            btn = QPushButton(f"    {name}")
            btn.setCheckable(True)
            btn.setFixedHeight(48)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding: 12px 16px;
                    border: none;
                    border-radius: 12px;
                    font-size: 14px;
                    color: {COLORS['text_muted']};
                    background: transparent;
                }}
                QPushButton:hover {{
                    background-color: #F8F9FA;
                    color: {COLORS['text']};
                }}
                QPushButton:checked {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #FFF3E0,
                        stop:1 white);
                    color: {COLORS['primary']};
                    font-weight: bold;
                }}
            """)
            btn.clicked.connect(lambda _, b=btn, k=key: self._on_nav_clicked(b, k))
            self.nav_group.append(btn)
            btn_layout.addWidget(btn, stretch=1)
            
            # 数量徽章
            if count > 0:
                badge = QLabel(str(count))
                badge.setFixedSize(24, 20)
                badge.setStyleSheet(f"""
                    QLabel {{
                        background-color: {COLORS['border']};
                        color: {COLORS['text_muted']};
                        border-radius: 10px;
                        font-size: 11px;
                        font-weight: bold;
                    }}
                """)
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                btn_layout.addWidget(badge)
                btn_layout.addSpacing(16) # 右侧留白
            
            self.month_container.addWidget(btn_widget)
