from PyQt6.QtCore import Qt
from qfluentwidgets import MessageBoxBase, SubtitleLabel, LineEdit

class InputDialog(MessageBoxBase):
    """通用的单行文本输入对话框"""
    def __init__(self, title: str, label: str, default_text: str = "", placeholder: str = "", parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.lineEdit = LineEdit(self)
        
        self.lineEdit.setText(default_text)
        self.lineEdit.setPlaceholderText(placeholder)
        self.lineEdit.setClearButtonEnabled(True)
        
        # 布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)
        # 如果需要 label 可以加，但通常 title 就够了，或者 placeholder
        # 这里我们把 label 作为 placeholder 或者 subtitle? 
        # 用户传入的 label 比如 "请输入新名称:"
        # 我们可以加个 BodyLabel，或者直接作为 placeholder
        
        # 既然 MessageBoxBase 有 titleLabel，我们可以再加个说明
        # 但为了简洁，如果是简单的输入，title 就够了
        # 如果 label 很有用，我们加上
        if label:
             from qfluentwidgets import BodyLabel
             self.viewLayout.addWidget(BodyLabel(label, self))
             self.viewLayout.addSpacing(8)

        self.viewLayout.addWidget(self.lineEdit)
        
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        
        self.widget.setMinimumWidth(360)
        
        # 选中所有文本方便修改
        self.lineEdit.selectAll()
        self.lineEdit.setFocus()

    def text(self) -> str:
        return self.lineEdit.text().strip()
