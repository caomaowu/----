
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
    'shadow': '#000000',
    'error': '#DC3545'
}

PRIMARY_COLOR = COLORS['primary']
APP_BG = COLORS['bg']

# 标签专用配色方案 (柔和色系)
TAG_PALETTE = [
    '#E3F2FD', # Blue
    '#E8F5E9', # Green
    '#F3E5F5', # Purple
    '#FFF3E0', # Orange
    '#FFEBEE', # Red
    '#E0F2F1', # Teal
    '#FCE4EC', # Pink
    '#FFF8E1', # Amber
    '#ECEFF1', # Blue Grey
    '#F9FBE7', # Lime
]

TAG_TEXT_PALETTE = [
    '#1565C0', # Blue
    '#2E7D32', # Green
    '#7B1FA2', # Purple
    '#EF6C00', # Orange
    '#C62828', # Red
    '#00695C', # Teal
    '#AD1457', # Pink
    '#F57F17', # Amber
    '#455A64', # Blue Grey
    '#827717', # Lime
]

# 特定标签的固定颜色映射 (可选)
PRESET_TAG_COLORS = {
    '#第一版': 0, # Blue
    '#第二版': 2, # Purple
    '#模具': 5,   # Teal
    '#铸件渣包流道': 3, # Orange
    '#产品': 1,   # Green
    '#模流报告': 6, # Pink
    '#压铸参数计算': 8, # Blue Grey
    '#压射参数': 4, # Red
}

def get_tag_colors(tag_text: str) -> tuple[str, str]:
    """
    根据标签文本返回 (背景色, 文字色)
    """
    if tag_text in PRESET_TAG_COLORS:
        idx = PRESET_TAG_COLORS[tag_text]
    else:
        # 使用哈希值确定的随机颜色
        idx = abs(hash(tag_text)) % len(TAG_PALETTE)
    
    return TAG_PALETTE[idx], TAG_TEXT_PALETTE[idx]
