from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QPushButton, QLabel, QVBoxLayout
from qfluentwidgets import MessageBoxBase, SubtitleLabel, PlainTextEdit

from dcpm.infra.config.user_config import load_user_config
from dcpm.ui.components.flow_layout import FlowLayout
from dcpm.ui.theme.colors import get_tag_colors

class TagDialog(MessageBoxBase):
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        
        # 1. 预设标签区域
        self.presetContainer = QWidget()
        self.presetLayout = FlowLayout(self.presetContainer, margin=0, spacing=8)
        
        config = load_user_config()
        self.chips = {}
        
        # 解析当前已有标签
        current_tags = [t.strip() for t in content.replace('\n', ',').replace(';', ',').split(',') if t.strip()]
        
        # 创建预设标签 Chips
        for tag in config.preset_tags:
            bg, fg = get_tag_colors(tag)
            btn = QPushButton(tag)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            
            # 样式：未选中时浅色背景，选中时深色背景
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {fg};
                    border: 1px solid {fg}40;
                    border-radius: 14px;
                    padding: 0 12px;
                    font-family: "Microsoft YaHei";
                    font-size: 12px;
                }}
                QPushButton:checked {{
                    background-color: {fg};
                    color: white;
                    border: 1px solid {fg};
                }}
                QPushButton:hover:!checked {{
                    border: 1px solid {fg};
                    background-color: {bg};
                }}
            """)
            
            if tag in current_tags:
                btn.setChecked(True)
                
            # 使用闭包绑定 tag
            btn.toggled.connect(lambda checked, t=tag: self.on_chip_toggled(t, checked))
            self.presetLayout.addWidget(btn)
            self.chips[tag] = btn

        # 2. 文本输入区域
        self.textEdit = PlainTextEdit(self)
        self.textEdit.setPlainText(content)
        self.textEdit.setPlaceholderText("用逗号分隔标签，例如：#第一版, #第二版")
        self.textEdit.setMinimumHeight(80)
        self.textEdit.setMinimumWidth(360)
        
        # 双向绑定：文本变动同步更新 Chip 状态
        self.textEdit.textChanged.connect(self.on_text_changed)

        # 3. 组装布局
        self.viewLayout.addWidget(self.titleLabel)
        
        if config.preset_tags:
            self.presetLabel = QLabel("快速选择：", self)
            self.presetLabel.setStyleSheet("color: #666; font-size: 12px; margin-top: 8px; margin-bottom: 4px;")
            self.viewLayout.addWidget(self.presetLabel)
            self.viewLayout.addWidget(self.presetContainer)
            
        self.viewLayout.addWidget(self.textEdit)

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(500) # 加宽以容纳更多标签

    def on_chip_toggled(self, tag: str, checked: bool):
        """当点击 Chip 时更新文本框"""
        self.textEdit.blockSignals(True)
        
        text = self.textEdit.toPlainText()
        # 清理并分割现有标签
        tags = [t.strip() for t in text.replace('\n', ',').replace(';', ',').split(',') if t.strip()]
        
        if checked:
            if tag not in tags:
                tags.append(tag)
        else:
            # 如果存在则移除
            if tag in tags:
                tags.remove(tag)
                
        # 重新组合文本
        self.textEdit.setPlainText(", ".join(tags))
        self.textEdit.blockSignals(False)

    def on_text_changed(self):
        """当手动修改文本时更新 Chip 状态"""
        text = self.textEdit.toPlainText()
        tags = [t.strip() for t in text.replace('\n', ',').replace(';', ',').split(',') if t.strip()]
        
        for tag, btn in self.chips.items():
            btn.blockSignals(True)
            btn.setChecked(tag in tags)
            btn.blockSignals(False)

    def get_text(self) -> str:
        return self.textEdit.toPlainText()
