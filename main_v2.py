# -*- coding: utf-8 -*-
import sys
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QBrush, QPen
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea,
    QFrame, QGridLayout, QSizePolicy, QGraphicsDropShadowEffect
)

from qfluentwidgets import (
    CardWidget, IconWidget, BodyLabel, CaptionLabel,
    SearchLineEdit, PillPushButton, SegmentedWidget, ToolButton,
    Theme, setTheme, setThemeColor, FluentIcon as FI
)


# ========== 颜色配置 ==========
COLORS = {
    'bg': '#F8F9FA',
    'card': '#FFFFFF',
    'primary': '#E65100',
    'primary_light': '#FF9800',
    'secondary': '#6C757D',
    'success': '#28A745',
    'warning': '#FFC107',
    'info': '#17A2B8',
    'text': '#212529',
    'text_muted': '#6C757D',
    'border': '#E9ECEF',
    'shadow': '#000000'
}


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
    """顶部统计卡片 - 类似参考UI的Transaction overview"""
    
    def __init__(self, title, value, subtitle, color, progress, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.title = title
        self.value = value
        self.subtitle = subtitle
        self.color = color
        self.progress = progress
        self.setupUI()
        
    def create_expandable_group(self, title, items, expanded=True):
        """创建可展开的分组"""
        group_container = QWidget()
        group_layout = QVBoxLayout(group_container)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(4)
        
        # 分组标题按钮
        header_btn = QPushButton(f"{'▼' if expanded else '▶'}  {title}")
        header_btn.setCheckable(True)
        header_btn.setChecked(expanded)
        header_btn.setFixedHeight(40)
        header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header_btn.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                padding: 10px 16px;
                border: none;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                color: {COLORS['text']};
                background: transparent;
            }}
            QPushButton:hover {{
                background-color: #F8F9FA;
            }}
        """)
        group_layout.addWidget(header_btn)
        
        # 子项容器
        items_container = QWidget()
        items_layout = QVBoxLayout(items_container)
        items_layout.setContentsMargins(16, 0, 0, 0)
        items_layout.setSpacing(4)
        
        # 子项样式
        def create_sub_item(text, count):
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(8)
            
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding: 8px 12px;
                    border: none;
                    border-radius: 8px;
                    font-size: 13px;
                    color: {COLORS['text_muted']};
                    background: transparent;
                }}
                QPushButton:hover {{
                    background-color: #F8F9FA;
                    color: {COLORS['text']};
                }}
                QPushButton:checked {{
                    background-color: #FFF3E0;
                    color: {COLORS['primary']};
                    font-weight: 500;
                }}
            """)
            item_layout.addWidget(btn, stretch=1)
            
            # 数量徽章
            badge = QLabel(count)
            badge.setFixedSize(28, 20)
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
            item_layout.addWidget(badge)
            
            return item_widget
        
        for text, count in items:
            items_layout.addWidget(create_sub_item(text, count))
        
        items_container.setVisible(expanded)
        group_layout.addWidget(items_container)
        
        # 点击展开/收起
        def toggle_expand():
            is_expanded = items_container.isVisible()
            items_container.setVisible(not is_expanded)
            header_btn.setText(f"{'▼' if not is_expanded else '▶'}  {title}")
        
        header_btn.clicked.connect(toggle_expand)
        
        return group_container
        
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
        value_label = QLabel(self.value)
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
        progress_bar.setFixedWidth(int(self.progress * 2))  # 简单模拟
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


class ProjectCard(ShadowCard):
    """精致的项目卡片"""
    
    def __init__(self, project_code, project_name, client, status, tags, date, parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 200)
        self.project_code = project_code
        self.project_name = project_name
        self.client = client
        self.status = status
        self.tags = tags
        self.date = date
        
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        
        # 顶部：图标和编号
        top_layout = QHBoxLayout()
        
        # 渐变背景图标
        icon_container = QWidget()
        icon_container.setFixedSize(48, 48)
        icon_container.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {COLORS['primary_light']},
                    stop:1 {COLORS['primary']});
                border-radius: 12px;
            }}
        """)
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon = IconWidget(FI.FOLDER)
        icon.setFixedSize(24, 24)
        icon.setStyleSheet("color: white;")
        icon_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        
        top_layout.addWidget(icon_container)
        top_layout.addSpacing(12)
        
        # 项目编号和名称
        name_layout = QVBoxLayout()
        name_layout.setSpacing(2)
        
        code_label = QLabel(self.project_code)
        code_label.setStyleSheet(f"color: {COLORS['primary']}; font-size: 11px; font-weight: bold;")
        name_layout.addWidget(code_label)
        
        name_label = QLabel(self.project_name)
        name_font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        name_label.setFont(name_font)
        name_label.setStyleSheet(f"color: {COLORS['text']};")
        name_layout.addWidget(name_label)
        
        top_layout.addLayout(name_layout)
        top_layout.addStretch()
        
        layout.addLayout(top_layout)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {COLORS['border']};")
        line.setFixedHeight(1)
        layout.addWidget(line)
        
        # 客户信息
        client_layout = QHBoxLayout()
        client_icon = IconWidget(FI.PEOPLE)
        client_icon.setFixedSize(16, 16)
        client_icon.setStyleSheet(f"color: {COLORS['text_muted']};")
        client_layout.addWidget(client_icon)
        
        client_label = QLabel(self.client)
        client_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 13px;")
        client_layout.addWidget(client_label)
        client_layout.addStretch()
        layout.addLayout(client_layout)
        
        layout.addStretch()
        
        # 底部：标签和状态
        bottom_layout = QHBoxLayout()
        
        # 标签
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(6)
        for tag in self.tags[:2]:  # 最多显示2个标签
            tag_btn = QLabel(f"#{tag}")
            tag_btn.setStyleSheet(f"""
                QLabel {{
                    background-color: #FFF3E0;
                    color: {COLORS['primary']};
                    border-radius: 10px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 500;
                }}
            """)
            tags_layout.addWidget(tag_btn)
        tags_layout.addStretch()
        bottom_layout.addLayout(tags_layout)
        
        bottom_layout.addStretch()
        
        # 状态指示器
        status_colors = {
            "量产": COLORS['success'],
            "试模": COLORS['warning'],
            "设计": COLORS['info'],
            "暂停": COLORS['secondary']
        }
        status_color = status_colors.get(self.status, COLORS['secondary'])
        
        status_widget = QWidget()
        status_widget.setFixedSize(8, 8)
        status_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {status_color};
                border-radius: 4px;
            }}
        """)
        bottom_layout.addWidget(status_widget)
        
        status_label = QLabel(self.status)
        status_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        bottom_layout.addWidget(status_label)
        
        layout.addLayout(bottom_layout)
        
        # 日期
        date_label = QLabel(self.date)
        date_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        layout.addWidget(date_label, alignment=Qt.AlignmentFlag.AlignRight)


class SidebarWidget(QWidget):
    """精致的左侧导航"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setupUI()
        
    def create_expandable_group(self, title, items, expanded=True):
        """创建可展开的分组"""
        group_container = QWidget()
        group_layout = QVBoxLayout(group_container)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(4)
        
        # 分组标题按钮
        header_btn = QPushButton(f"{'▼' if expanded else '▶'}  {title}")
        header_btn.setCheckable(True)
        header_btn.setChecked(expanded)
        header_btn.setFixedHeight(40)
        header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header_btn.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                padding: 10px 16px;
                border: none;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                color: {COLORS['text']};
                background: transparent;
            }}
            QPushButton:hover {{
                background-color: #F8F9FA;
            }}
        """)
        group_layout.addWidget(header_btn)
        
        # 子项容器
        items_container = QWidget()
        items_layout = QVBoxLayout(items_container)
        items_layout.setContentsMargins(16, 0, 0, 0)
        items_layout.setSpacing(4)
        
        # 子项样式
        def create_sub_item(text, count):
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(8)
            
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding: 8px 12px;
                    border: none;
                    border-radius: 8px;
                    font-size: 13px;
                    color: {COLORS['text_muted']};
                    background: transparent;
                }}
                QPushButton:hover {{
                    background-color: #F8F9FA;
                    color: {COLORS['text']};
                }}
                QPushButton:checked {{
                    background-color: #FFF3E0;
                    color: {COLORS['primary']};
                    font-weight: 500;
                }}
            """)
            item_layout.addWidget(btn, stretch=1)
            
            # 数量徽章
            badge = QLabel(count)
            badge.setFixedSize(28, 20)
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
            item_layout.addWidget(badge)
            
            return item_widget
        
        for text, count in items:
            items_layout.addWidget(create_sub_item(text, count))
        
        items_container.setVisible(expanded)
        group_layout.addWidget(items_container)
        
        # 点击展开/收起
        def toggle_expand():
            is_expanded = items_container.isVisible()
            items_container.setVisible(not is_expanded)
            header_btn.setText(f"{{'▼' if not is_expanded else '▶'}}  {title}")
        
        header_btn.clicked.connect(toggle_expand)
        
        return group_container
        
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
        logo_font = QFont("Microsoft YaHei", 18, QFont.Weight.Bold)
        logo_text.setFont(logo_font)
        logo_text.setStyleSheet(f"color: {COLORS['text']};")
        logo_layout.addWidget(logo_text)
        logo_layout.addStretch()
        
        layout.addWidget(logo_container)
        layout.addSpacing(40)
        
        # 导航样式
        def create_nav_btn(text, icon_name=None, checked=False):
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
            return btn
        
        # 主导航
        self.all_btn = create_nav_btn("📁   全部项目", checked=True)
        layout.addWidget(self.all_btn)
        
        self.fav_btn = create_nav_btn("⭐   收藏项目")
        layout.addWidget(self.fav_btn)
        
        layout.addSpacing(24)
        
        # 月份分组
        month_header = QLabel("📅 按月份")
        month_header.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: bold; padding: 8px 16px;")
        layout.addWidget(month_header)
        
        months = [
            ("2024年03月", "3"),
            ("2024年02月", "5"),
            ("2024年01月", "8"),
        ]
        for month, count in months:
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            
            btn = create_nav_btn(f"    {month}")
            btn_layout.addWidget(btn, stretch=1)
            
            # 数量徽章
            badge = QLabel(count)
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
            
            layout.addWidget(btn_widget)
        
        layout.addSpacing(24)
        
        # 快速筛选
        filter_header = QLabel("⚡ 快速筛选")
        filter_header.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-weight: bold; padding: 8px 16px;")
        layout.addWidget(filter_header)
        
        filters = ["进行中", "待审核", "已归档"]
        for f in filters:
            btn = create_nav_btn(f"    {f}")
            layout.addWidget(btn)
        
        layout.addSpacing(24)
        
        # ========== 按文档类型 - 可展开分组 ==========
        self.doc_group = self.create_expandable_group(
            "📂 按文档类型",
            [
                ("📐  3D文件", "45"),
                ("📄  技术文档", "32"),
                ("📊  模流分析", "18"),
                ("📷  照片记录", "67"),
            ],
            expanded=True  # 默认展开
        )
        layout.addWidget(self.doc_group)
        
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
        email_label = QLabel("admin@company.com")
        email_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        info_layout.addWidget(email_label)
        user_layout.addLayout(info_layout)
        
        user_layout.addStretch()
        
        # 设置按钮
        settings_btn = ToolButton(FI.SETTING)
        settings_btn.setFixedSize(32, 32)
        settings_btn.setStyleSheet(f"color: {COLORS['text_muted']};")
        user_layout.addWidget(settings_btn)
        
        layout.addWidget(user_card)


class RightPanel(QWidget):
    """精致的右侧面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 28)
        layout.setSpacing(20)
        
        # 搜索框 - 更精致
        self.search_box = SearchLineEdit()
        self.search_box.setPlaceholderText("搜索项目、客户、标签...")
        self.search_box.setFixedHeight(48)
        self.search_box.setStyleSheet(f"""
            SearchLineEdit {{
                background-color: {COLORS['card']};
                border: 2px solid {COLORS['border']};
                border-radius: 12px;
                padding: 0 16px;
                font-size: 14px;
            }}
            SearchLineEdit:focus {{
                border-color: {COLORS['primary']};
            }}
        """)
        layout.addWidget(self.search_box)
        
        # 快捷操作
        quick_card = ShadowCard()
        quick_layout = QVBoxLayout(quick_card)
        quick_layout.setContentsMargins(20, 20, 20, 20)
        quick_layout.setSpacing(16)
        
        quick_title = QLabel("⚡ 快捷操作")
        quick_title.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: bold;")
        quick_layout.addWidget(quick_title)
        
        actions = [
            ("➕  新建项目", COLORS['primary']),
            ("📊  生成报表", COLORS['info']),
            ("📤  导出数据", COLORS['success']),
        ]
        for text, color in actions:
            btn = QPushButton(text)
            btn.setFixedHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg']};
                    color: {COLORS['text']};
                    border: none;
                    border-radius: 10px;
                    font-size: 13px;
                    text-align: left;
                    padding: 0 16px;
                }}
                QPushButton:hover {{
                    background-color: {color}15;
                    color: {color};
                }}
            """)
            quick_layout.addWidget(btn)
        
        layout.addWidget(quick_card)
        
        # 热门标签
        tags_card = ShadowCard()
        tags_layout = QVBoxLayout(tags_card)
        tags_layout.setContentsMargins(20, 20, 20, 20)
        tags_layout.setSpacing(16)
        
        tags_title = QLabel("🏷️ 热门标签")
        tags_title.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: bold;")
        tags_layout.addWidget(tags_title)
        
        tags_grid = QGridLayout()
        tags_grid.setSpacing(8)
        popular_tags = [
            ("试模", "12"),
            ("气孔", "8"),
            ("量产", "15"),
            ("变速箱", "5"),
            ("DFM", "6"),
            ("分析", "4"),
        ]
        for i, (tag, count) in enumerate(popular_tags):
            btn = QPushButton(f"#{tag}  {count}")
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg']};
                    color: {COLORS['text_muted']};
                    border: none;
                    border-radius: 8px;
                    font-size: 12px;
                }}
                QPushButton:checked {{
                    background-color: {COLORS['primary']};
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['border']};
                }}
            """)
            tags_grid.addWidget(btn, i // 2, i % 2)
        
        tags_layout.addLayout(tags_grid)
        layout.addWidget(tags_card)
        
        # 最近活动
        activity_card = ShadowCard()
        activity_layout = QVBoxLayout(activity_card)
        activity_layout.setContentsMargins(20, 20, 20, 20)
        activity_layout.setSpacing(16)
        
        activity_title = QLabel("🕐 最近动态")
        activity_title.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: bold;")
        activity_layout.addWidget(activity_title)
        
        activities = [
            ("创建了 PRJ-202403-002", "2分钟前", COLORS['success']),
            ("上传了 DFM 报告", "1小时前", COLORS['info']),
            ("添加标签 #试模", "3小时前", COLORS['warning']),
            ("完成项目 PRJ-202401-008", "昨天", COLORS['primary']),
        ]
        
        for act, time, color in activities:
            item = QWidget()
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(12)
            
            # 指示点
            dot = QWidget()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"""
                QWidget {{
                    background-color: {color};
                    border-radius: 4px;
                }}
            """)
            item_layout.addWidget(dot)
            
            # 内容
            content_layout = QVBoxLayout()
            content_layout.setSpacing(2)
            act_label = QLabel(act)
            act_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px;")
            content_layout.addWidget(act_label)
            time_label = QLabel(time)
            time_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
            content_layout.addWidget(time_label)
            item_layout.addLayout(content_layout, stretch=1)
            
            activity_layout.addWidget(item)
        
        layout.addWidget(activity_card)
        layout.addStretch()


class MainContent(QWidget):
    """主内容区 - 精致版"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)
        
        # 标题区
        header_layout = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        
        title = QLabel("全部项目")
        title_font = QFont("Microsoft YaHei", 28, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {COLORS['text']};")
        title_layout.addWidget(title)
        
        subtitle = QLabel("管理和追踪您的压铸项目，共 28 个项目")
        subtitle.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px;")
        title_layout.addWidget(subtitle)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        
        # 视图切换
        self.view_switch = SegmentedWidget()
        self.view_switch.addItem("grid", "⊞ 网格", lambda: None)
        self.view_switch.addItem("list", "☰ 列表", lambda: None)
        self.view_switch.addItem("timeline", "◷ 时间线", lambda: None)
        self.view_switch.setCurrentItem("grid")
        header_layout.addWidget(self.view_switch)
        
        layout.addLayout(header_layout)
        
        # 统计概览栏 - 类似参考UI的设计
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(20)
        
        stats = [
            ("本月新建", "3", "较上月 +1", COLORS['primary'], 60),
            ("进行中", "5", "活跃项目", COLORS['info'], 40),
            ("本月完成", "8", "已归档", COLORS['success'], 80),
            ("平均进度", "68%", "整体进度", COLORS['warning'], 68),
        ]
        
        for title, value, subtitle, color, progress in stats:
            stat_card = StatCard(title, value, subtitle, color, progress)
            stats_layout.addWidget(stat_card)
        
        layout.addLayout(stats_layout)
        
        # 筛选栏
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)
        
        # 筛选按钮
        for text in ["📁 全部状态 ▼", "📅 全部时间 ▼", "🏷️ 全部标签 ▼"]:
            btn = QPushButton(text)
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['card']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 10px;
                    padding: 0 16px;
                    color: {COLORS['text']};
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    border-color: {COLORS['primary']};
                    color: {COLORS['primary']};
                }}
            """)
            filter_layout.addWidget(btn)
        
        filter_layout.addStretch()
        
        # 排序
        sort_btn = QPushButton("⇅ 最近更新")
        sort_btn.setFixedHeight(40)
        sort_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {COLORS['text_muted']};
                font-size: 13px;
            }}
            QPushButton:hover {{
                color: {COLORS['primary']};
            }}
        """)
        filter_layout.addWidget(sort_btn)
        
        layout.addLayout(filter_layout)
        
        # 项目网格
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")
        
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(24)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        
        # 示例项目数据
        projects = [
            ("PRJ-202403-001", "变速箱壳体", "东风汽车", "试模", ["试模", "气孔"], "2024-03-15"),
            ("PRJ-202403-002", "发动机支架", "一汽集团", "量产", ["量产", "支架"], "2024-03-12"),
            ("PRJ-202403-003", "刹车盘壳体", "比亚迪", "设计", ["DFM", "分析"], "2024-03-10"),
            ("PRJ-202402-001", "转向机壳体", "吉利汽车", "试模", ["试模"], "2024-02-28"),
            ("PRJ-202402-002", "油底壳总成", "长城汽车", "量产", ["量产", "外壳"], "2024-02-20"),
            ("PRJ-202402-003", "水泵壳体", "长安汽车", "试模", ["试模", "改进"], "2024-02-15"),
            ("PRJ-202401-001", "差速器壳体", "奇瑞汽车", "量产", ["量产", "完成"], "2024-01-25"),
            ("PRJ-202401-002", "离合器壳体", "上汽集团", "暂停", ["暂停", "待料"], "2024-01-18"),
        ]
        
        row, col = 0, 0
        for code, name, client, status, tags, date in projects:
            card = ProjectCard(code, name, client, status, tags, date)
            self.grid_layout.addWidget(card, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1
        
        self.grid_layout.setRowStretch(row + 1, 1)
        
        scroll.setWidget(self.grid_widget)
        layout.addWidget(scroll)


class MainWindow(QWidget):
    """主窗口 - 精致版"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("压铸项目管理系统 Pro")
        self.setMinimumSize(1600, 1000)
        self.resize(1800, 1100)
        self.setupUI()
        
    def setupUI(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 左侧导航
        self.sidebar = SidebarWidget()
        main_layout.addWidget(self.sidebar)
        
        # 中间内容
        self.main_content = MainContent()
        main_layout.addWidget(self.main_content, 1)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"background-color: {COLORS['border']};")
        line.setFixedWidth(1)
        main_layout.addWidget(line)
        
        # 右侧面板
        self.right_panel = RightPanel()
        main_layout.addWidget(self.right_panel)
        
        # 全局样式
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['bg']};
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
            }}
        """)


def main():
    setTheme(Theme.LIGHT)
    setThemeColor("#E65100")
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
