from PyQt6.QtCore import Qt, QSize, QModelIndex, QRect
from PyQt6.QtGui import QPainter, QColor, QIcon, QPixmap, QFileSystemModel
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle

from dcpm.ui.theme.colors import COLORS, get_tag_colors

class FileItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, tag_provider=None, thumbnail_provider=None):
        super().__init__(parent)
        self.margins = 8
        self.icon_size = 48
        self.tag_provider = tag_provider
        self.thumbnail_provider = thumbnail_provider
        self.view_mode = "icon" # "icon" or "list"

    def set_view_mode(self, mode: str):
        self.view_mode = mode

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        if self.view_mode == "list":
            return QSize(option.rect.width(), 36)
        return QSize(100, 130)  # Width, Height for grid items

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect

        # Draw background for selection/hover
        if option.state & QStyle.StateFlag.State_Selected:
            # List mode selection style
            if self.view_mode == "list":
                painter.setBrush(QColor(COLORS['primary_light']))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)
            else:
                painter.setBrush(QColor(COLORS['primary_light']))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 8, 8)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            if self.view_mode == "list":
                painter.setBrush(QColor(COLORS['bg']))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)
            else:
                painter.setBrush(QColor(COLORS['bg'])) # Slightly darker than app bg
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 8, 8)

        # 获取数据
        file_path = ""
        model = index.model()
        if isinstance(model, QFileSystemModel):
            file_path = model.filePath(index)

        # --- 列表模式渲染 ---
        if self.view_mode == "list":
            icon_size = 24
            padding = 8
            
            # 1. 图标
            icon_rect = QRect(rect.x() + padding, rect.y() + (rect.height() - icon_size)//2, icon_size, icon_size)
            
            # Try Thumbnail first
            icon_drawn = False
            if self.thumbnail_provider and file_path:
                thumb = self.thumbnail_provider.get_thumbnail(file_path)
                if thumb:
                    scaled = thumb.scaled(
                        icon_size, icon_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    # Center in icon_rect
                    tx = icon_rect.x() + (icon_size - scaled.width()) // 2
                    ty = icon_rect.y() + (icon_size - scaled.height()) // 2
                    painter.drawPixmap(tx, ty, scaled)
                    icon_drawn = True

            # Fallback to Icon
            if not icon_drawn:
                icon_q = index.data(Qt.ItemDataRole.DecorationRole)
                if icon_q:
                    pixmap = icon_q.pixmap(icon_size, icon_size)
                    painter.drawPixmap(icon_rect.x(), icon_rect.y(), pixmap)
            
            # 2. 文件名
            name = index.data(Qt.ItemDataRole.DisplayRole)
            text_x = icon_rect.right() + 12
            
            # 计算标签宽度
            tags = []
            if callable(self.tag_provider):
                try:
                    tags = list(self.tag_provider(index) or [])
                except Exception:
                    tags = []
            
            tag_width = 0
            if tags:
                # 预估标签宽度
                fm_tag = painter.fontMetrics()
                # 简单估算：每个标签大约 60px? 准确计算比较好
                # 列表模式只显示前 3 个
                display_tags = tags[:3]
                if len(tags) > 3:
                    display_tags.append(f"+{len(tags)-3}")
                
                # 标签放在右侧
                tag_gap = 6
                tag_padding = 12 # inner padding sum
                for t in display_tags:
                    tag_width += fm_tag.horizontalAdvance(t) + tag_padding + tag_gap
            
            text_width = rect.width() - text_x - tag_width - padding
            text_rect = QRect(text_x, rect.y(), text_width, rect.height())
            
            painter.setPen(QColor(COLORS['text']))
            elided_text = option.fontMetrics.elidedText(name, Qt.TextElideMode.ElideMiddle, text_rect.width())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_text)
            
            # 3. 标签 (右对齐)
            if tags:
                tag_x = rect.right() - padding - tag_width + 12 # adjust
                tag_y = rect.y() + (rect.height() - 20) // 2 # 20px height for tags
                
                display_tags = tags[:3]
                if len(tags) > 3:
                    display_tags.append(f"+{len(tags)-3}")

                tag_font = option.font
                tag_font.setPointSize(9)
                painter.setFont(tag_font)
                fm2 = painter.fontMetrics()
                
                for t in display_tags:
                    bg_hex, text_hex = get_tag_colors(t)
                    w = fm2.horizontalAdvance(t) + 12
                    chip_rect = QRect(tag_x, tag_y, w, 20)
                    
                    painter.setBrush(QColor(bg_hex))
                    border_color = QColor(text_hex)
                    border_color.setAlpha(80)
                    painter.setPen(border_color)
                    painter.drawRoundedRect(chip_rect, 4, 4) # smaller radius
                    
                    painter.setPen(QColor(text_hex))
                    painter.drawText(chip_rect, Qt.AlignmentFlag.AlignCenter, t)
                    
                    tag_x += w + 6

            painter.restore()
            return

        # --- 图标模式渲染 (保持原有逻辑) ---
        
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

        # Draw Icon or Thumbnail
        icon_drawn = False
        
        # Try Thumbnail first
        if self.thumbnail_provider and file_path:
             thumb = self.thumbnail_provider.get_thumbnail(file_path)
             if thumb:
                 # Scale thumbnail to fit within (icon_size, icon_size) preserving aspect ratio
                 scaled_thumb = thumb.scaled(
                     self.icon_size, self.icon_size,
                     Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation
                 )
                 
                 # Center the thumbnail
                 tx = icon_x + (self.icon_size - scaled_thumb.width()) // 2
                 ty = icon_y + (self.icon_size - scaled_thumb.height()) // 2
                 
                 painter.drawPixmap(tx, ty, scaled_thumb)
                 icon_drawn = True

        # Fallback to Icon
        if not icon_drawn:
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
