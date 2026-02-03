from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGridLayout
from qfluentwidgets import SearchLineEdit

from dcpm.ui.theme.colors import COLORS
from dcpm.ui.components.cards import ShadowCard

class RightPanel(QWidget):
    """精致的右侧面板"""
    
    searchChanged = pyqtSignal(str)
    actionTriggered = pyqtSignal(str) # "create", "rebuild", "report", etc.
    tagSelected = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self.setupUI()
        self._popular_tags = []
        self._recent_activities = []
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 28)
        layout.setSpacing(20)
        
        # 搜索框
        self.search_box = SearchLineEdit()
        self.search_box.setPlaceholderText("搜索项目、客户、标签...")
        self.search_box.setFixedHeight(40)
        self.search_box.setStyleSheet(f"""
            SearchLineEdit {{
                background-color: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
                padding: 0 12px;
                font-size: 13px;
            }}
            SearchLineEdit:focus {{
                border-color: {COLORS['primary']};
            }}
        """)
        self.search_box.textChanged.connect(self.searchChanged)
        layout.addWidget(self.search_box)
        
        # 快捷操作
        quick_card = ShadowCard()
        quick_layout = QVBoxLayout(quick_card)
        quick_layout.setContentsMargins(20, 20, 20, 20)
        quick_layout.setSpacing(12)
        
        quick_title = QLabel("⚡ 快捷操作")
        quick_title.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: bold;")
        quick_layout.addWidget(quick_title)
        
        actions = [
            ("➕  新建项目", COLORS['primary'], "create"),
            ("🔄  重建索引", COLORS['info'], "rebuild"),
            ("📂  选择库", COLORS['secondary'], "pick_lib"),
        ]
        for text, color, action_key in actions:
            btn = QPushButton(text)
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg']};
                    color: {COLORS['text']};
                    border: none;
                    border-radius: 8px;
                    font-size: 13px;
                    text-align: left;
                    padding: 0 16px;
                }}
                QPushButton:hover {{
                    background-color: {color}15;
                    color: {color};
                }}
            """)
            btn.clicked.connect(lambda _, k=action_key: self.actionTriggered.emit(k))
            quick_layout.addWidget(btn)
        
        layout.addWidget(quick_card)
        
        # 热门标签
        tags_card = ShadowCard()
        self.tags_layout = QVBoxLayout(tags_card)
        self.tags_layout.setContentsMargins(20, 20, 20, 20)
        self.tags_layout.setSpacing(16)
        
        tags_title = QLabel("🏷️ 热门标签")
        tags_title.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: bold;")
        self.tags_layout.addWidget(tags_title)
        
        self.tags_grid = QGridLayout()
        self.tags_grid.setSpacing(8)
        self.tags_layout.addLayout(self.tags_grid)
        
        layout.addWidget(tags_card)
        
        # 最近活动
        activity_card = ShadowCard()
        self.activity_layout = QVBoxLayout(activity_card)
        self.activity_layout.setContentsMargins(20, 20, 20, 20)
        self.activity_layout.setSpacing(16)
        
        activity_title = QLabel("🕐 最近动态")
        activity_title.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: bold;")
        self.activity_layout.addWidget(activity_title)
        
        self.activity_container = QVBoxLayout()
        self.activity_container.setSpacing(12)
        self.activity_layout.addLayout(self.activity_container)
        
        layout.addWidget(activity_card)
        layout.addStretch()

    def update_tags(self, tags: list[tuple[str, int]], selected_tags: set[str]):
        # 清除旧标签
        while self.tags_grid.count():
            item = self.tags_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        for i, (tag, count) in enumerate(tags[:10]): # Top 10
            btn = QPushButton(f"#{tag}  {count}")
            btn.setCheckable(True)
            btn.setChecked(tag in selected_tags)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # 选中状态样式
            bg = COLORS['primary'] if tag in selected_tags else COLORS['bg']
            fg = "white" if tag in selected_tags else COLORS['text_muted']
            
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {fg};
                    border: none;
                    border-radius: 6px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['primary'] if tag in selected_tags else COLORS['border']};
                }}
            """)
            btn.clicked.connect(lambda _, t=tag: self.tagSelected.emit(t))
            self.tags_grid.addWidget(btn, i // 2, i % 2)

    def update_activities(self, activities: list[tuple[str, str, str]]):
        # activities: [(text, time, color_hex), ...]
        while self.activity_container.count():
            item = self.activity_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        for act, time, color in activities[:5]:
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
            act_label.setWordWrap(True)
            act_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px;")
            content_layout.addWidget(act_label)
            time_label = QLabel(time)
            time_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
            content_layout.addWidget(time_label)
            item_layout.addLayout(content_layout, stretch=1)
            
            self.activity_container.addWidget(item)
        
        if not activities:
            lbl = QLabel("暂无动态")
            lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
            self.activity_container.addWidget(lbl)
