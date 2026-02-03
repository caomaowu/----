from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel
)
from PyQt6.QtCore import Qt
from qfluentwidgets import (
    PlainTextEdit, PrimaryPushButton, PushButton, MessageBoxBase, SubtitleLabel
)
from dcpm.ui.theme.colors import COLORS

class NoteDialog(MessageBoxBase):
    """ Custom Note Dialog """

    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.content = content
        
        # Text Editor
        self.textEdit = PlainTextEdit(self)
        self.textEdit.setPlainText(content)
        self.textEdit.setPlaceholderText("请输入备注内容...")
        self.textEdit.setMinimumHeight(150)
        self.textEdit.setMinimumWidth(300)
        
        # Style
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.textEdit)
        
        # Customize buttons
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        
        self.widget.setMinimumWidth(350)

    def get_text(self) -> str:
        return self.textEdit.toPlainText()
