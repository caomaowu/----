from PyQt6.QtCore import Qt, QSize, QModelIndex, QRect
from PyQt6.QtGui import QPainter, QColor, QIcon
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle

from dcpm.ui.theme.colors import COLORS, get_tag_colors

class FileItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, tag_provider=None):
        super().__init__(parent)
        self.margins = 8
        self.icon_size = 48
        self.tag_provider = tag_provider
        
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(100, 130)  # Width, Height for grid items

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect

        # Draw background for selection/hover
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QColor(COLORS['primary_light']))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 8, 8)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setBrush(QColor(COLORS['bg'])) # Slightly darker than app bg
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 8, 8)

        # --- 布局计算 (自上而下) ---
        
        # 1. 图标区域 (固定在顶部)
        icon_top_margin = 12
        icon_x = rect.x() + (rect.width() - self.icon_size) // 2
        icon_y = rect.y() + icon_top_margin
        
        # 2. 文本区域 (在图标下方)
        text_top_gap = 8
        text_y = icon_y + self.icon_size + text_top_gap
        fm = option.fontMetrics
        text_height = fm.height()
        text_rect = QRect(rect.x() + 4, text_y, rect.width() - 8, text_height)

        # 3. 标签区域 (在文本下方)
        tag_top_gap = 6
        tag_y = text_y + text_height + tag_top_gap

        # --- 开始绘制 ---

        # Draw Icon
        icon: QIcon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon:
            pixmap = icon.pixmap(self.icon_size, self.icon_size)
            painter.drawPixmap(icon_x, icon_y, pixmap)

        # Draw Text
        name: str = index.data(Qt.ItemDataRole.DisplayRole)
        painter.setPen(QColor(COLORS['text']))
        
        # Elide text if too long
        elided_text = fm.elidedText(name, Qt.TextElideMode.ElideMiddle, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided_text)

        # Draw Tags
        tags: list[str] = []
        if callable(self.tag_provider):
            try:
                tags = list(self.tag_provider(index) or [])
            except Exception:
                tags = []

        if tags:
            # 优先显示前两个，多的显示 +N
            display_tags = tags[:2]
            more_count = max(0, len(tags) - 2)
            
            if more_count > 0:
                display_tags.append(f"+{more_count}")

            tag_font = option.font
            if tag_font.pointSize() > 9:
                tag_font.setPointSize(tag_font.pointSize() - 2)
            painter.setFont(tag_font)
            fm2 = painter.fontMetrics()

            pad_x = 6
            pad_y = 2
            gap = 6
            chip_h = fm2.height() + pad_y * 2
            
            widths = [fm2.horizontalAdvance(t) + pad_x * 2 for t in display_tags]
            total_w = sum(widths) + gap * (len(widths) - 1)
            
            # 计算标签行的起始 X (居中)
            tag_x = rect.x() + max(0, (rect.width() - total_w) // 2)

            for t, w in zip(display_tags, widths):
                # 获取该标签对应的配色
                bg_hex, text_hex = get_tag_colors(t)
                
                chip_rect = QRect(tag_x, tag_y, w, chip_h)
                
                # 绘制背景 (纯色，不透明或微调)
                painter.setBrush(QColor(bg_hex))
                
                # 绘制边框 (稍微透明一点的文字色，或者无边框)
                border_color = QColor(text_hex)
                border_color.setAlpha(80) 
                painter.setPen(border_color)
                
                painter.drawRoundedRect(chip_rect, 8, 8)
                
                # 绘制文字
                painter.setPen(QColor(text_hex))
                painter.drawText(chip_rect, Qt.AlignmentFlag.AlignCenter, t)
                
                tag_x += w + gap
        
        painter.restore()
