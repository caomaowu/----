from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget
)
from qfluentwidgets import (
    BodyLabel, CardWidget, SegmentedWidget, SubtitleLabel,
    FluentIcon as FI, IconWidget
)

from dcpm.ui.theme.colors import APP_BG, COLORS
from dcpm.infra.config.user_config import UserConfig, load_user_config, save_user_config
from dcpm.services.project_service import (
    CreateProjectRequest, archive_project, create_project, edit_project_metadata,
    unarchive_project
)
from dcpm.services.library_service import ProjectEntry
from dcpm.services.index_service import (
    DashboardStats,
    get_dashboard_stats,
    get_recent_activity,
    mark_opened_now,
    rebuild_index,
    search,
    toggle_pinned,
    upsert_one_project,
)
from dcpm.ui.components.project_card import ProjectCard, ProjectCardOptions
from dcpm.ui.components.cards import StatCard
from dcpm.ui.views.sidebar import SidebarWidget
from dcpm.ui.views.right_panel import RightPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("压铸项目管理系统")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)
        self.setStyleSheet(f"background: {APP_BG}; font-family: 'Segoe UI', 'Microsoft YaHei';")

        root = QWidget(self)
        self.setCentralWidget(root)

        # Global Layout: Sidebar | Main | RightPanel
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._cfg = load_user_config()
        self._library_root = self._cfg.library_root
        self._all_projects: list[ProjectEntry] = []
        self._filtered_projects: list[ProjectEntry] = []
        self._view_mode = "grid"
        self._status_filter = "all"
        self._time_filter = "all"
        self._search_query = ""
        self._auto_index_attempted = False

        # 1. Sidebar
        self._sidebar = SidebarWidget(self)
        self._sidebar.navChanged.connect(self._on_nav_changed)
        layout.addWidget(self._sidebar)

        # 2. Main Content
        self._main = self._build_main_content()
        layout.addWidget(self._main, 1)  # Stretch

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"background-color: {COLORS['border']};")
        line.setFixedWidth(1)
        layout.addWidget(line)

        # 3. Right Panel
        self._right_panel = RightPanel(self)
        self._right_panel.searchChanged.connect(self._on_search_changed)
        self._right_panel.actionTriggered.connect(self._on_action_triggered)
        self._right_panel.tagSelected.connect(self._on_tag_selected)
        layout.addWidget(self._right_panel)

        self._reload_projects()

    def _build_main_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)

        self._title_label = QLabel("全部项目")
        self._title_label.setFont(QFont("Microsoft YaHei", 24, QFont.Weight.Bold))
        self._title_label.setStyleSheet(f"color: {COLORS['text']};")
        title_layout.addWidget(self._title_label)

        self._subtitle_label = QLabel("正在加载...")
        self._subtitle_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px;")
        title_layout.addWidget(self._subtitle_label)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        # View Switcher
        self._view_switch = SegmentedWidget()
        self._view_switch.addItem("grid", "⊞ 网格", lambda: self._on_view_changed("grid"))
        self._view_switch.addItem("list", "☰ 列表", lambda: self._on_view_changed("list"))
        self._view_switch.addItem("timeline", "◷ 时间线", lambda: self._on_view_changed("timeline"))
        self._view_switch.setCurrentItem("grid")
        header_layout.addWidget(self._view_switch)

        layout.addLayout(header_layout)

        # Stats Bar
        self._stats_layout = QHBoxLayout()
        self._stats_layout.setSpacing(20)
        # Placeholders
        for _ in range(4):
            self._stats_layout.addWidget(StatCard("-", "0", "-", COLORS["secondary"], 0))
        layout.addLayout(self._stats_layout)

        # Filter Bar (Visual only for now, logic via sidebar)
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)

        btn_style = f"""
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
        """

        self._filter_btns = []
        for text in ["📁 全部状态", "📅 全部时间", "🏷️ 全部标签"]:
            btn = QPushButton(text + " ▼")
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(self._reset_filters)
            filter_layout.addWidget(btn)
            self._filter_btns.append(btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Project Scroll Area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")

        self._grid_container = QWidget()
        # 初始给一个空 layout，防止 _rebuild_grid 前的空白期
        QVBoxLayout(self._grid_container).setContentsMargins(0, 0, 0, 0)

        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll)

        return container

    def _update_stats(self, stats: DashboardStats):
        # Clear old stats
        while self._stats_layout.count():
            item = self._stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total = stats.total_projects
        ongoing = stats.processing_count
        delivered = stats.completed_count
        new_this_month = stats.new_this_month

        items = [
            ("本月新建", str(new_this_month), "较上月 --", COLORS["primary"], min(1.0, new_this_month / 10)),
            ("进行中", str(ongoing), "活跃项目", COLORS["info"], min(1.0, ongoing / max(1, total))),
            ("已交付", str(delivered), "本月完成", COLORS["success"], min(1.0, delivered / max(1, total))),
            ("项目总数", str(total), "全部项目", COLORS["warning"], 1.0),
        ]

        for title, value, subtitle, color, progress in items:
            self._stats_layout.addWidget(StatCard(title, value, subtitle, color, progress))

    def _reload_projects(self) -> None:
        if not self._library_root:
            self._all_projects = []
            self._filtered_projects = []
            self._rebuild_grid()
            return

        # 1. Load Projects (Full List)
        # Default includes archived only if filtered, but here we load all for client-side filtering flexibility
        # unless database grows huge. For now, load all (or top 200).
        # Actually, let's load what we need based on filter, but `search` with empty query gets top N.
        # If we want accurate client-side filtering for "all", we might need more than default limit.
        # But for MVP, default limit is fine.
        include_archived = self._status_filter == "archived" or self._status_filter == "all"
        result = search(Path(self._library_root), "", include_archived=True, limit=500)

        # Auto-index check
        if (not self._auto_index_attempted) and (not result.entries):
            self._auto_index_attempted = True
            try:
                db = rebuild_index(Path(self._library_root), include_archived=True)
                self._update_index_status(db.fts5_enabled)
                result = search(Path(self._library_root), "", include_archived=True, limit=500)
            except Exception:
                pass
        else:
            self._update_index_status(result.fts5_enabled)

        self._all_projects = result.entries

        # 2. Load Dashboard Stats (Global)
        try:
            stats = get_dashboard_stats(Path(self._library_root))
            self._update_stats(stats)
            self._update_sidebar_data(stats)
            self._update_right_panel_data(stats)
        except Exception:
            # Fallback if DB issues
            pass

        self._apply_filter()

    def _update_sidebar_data(self, stats: DashboardStats):
        # Format for Sidebar: [(name, key, count), ...]
        display_months = []
        for month, count in stats.month_counts:
            # month is "YYYY-MM"
            display_months.append((month, f"month:{month}", count))
        self._sidebar.update_months(display_months)

    def _update_right_panel_data(self, stats: DashboardStats):
        # Tags
        self._right_panel.update_tags(stats.popular_tags, set())

        # Activities
        try:
            raw_acts = get_recent_activity(Path(self._library_root))
            activities = []
            for act in raw_acts:
                # act: {id, name, customer, status, time}
                name = act["name"]
                time_str = datetime.fromisoformat(act["time"]).strftime("%m-%d %H:%M")
                status = act["status"]
                
                color = COLORS["info"]
                if status == "completed" or status == "delivered":
                    color = COLORS["success"]
                elif status == "archived":
                    color = COLORS["secondary"]
                
                activities.append((f"操作了项目 {name}", time_str, color))
            self._right_panel.update_activities(activities)
        except Exception:
            pass

    def _apply_filter(self) -> None:
        q = self._search_query.lower()
        filtered = []

        for entry in self._all_projects:
            # 1. Status / Nav Filter
            if self._status_filter != "all":
                if self._status_filter == "pinned":
                    if not entry.pinned:
                        continue
                elif self._status_filter.startswith("status:"):
                    status = self._status_filter.split(":")[1]
                    if entry.project.status != status:
                        continue
                elif self._status_filter.startswith("month:"):
                    month = self._status_filter.split(":")[1]
                    if entry.project.create_time.strftime("%Y-%m") != month:
                        continue

            # 2. Search Query
            if q:
                text = f"{entry.project.id} {entry.project.name} {entry.project.customer} {' '.join(entry.project.tags)}".lower()
                if q not in text:
                    continue

            # 3. Archive Hiding (default hidden unless viewing archived)
            if entry.project.status == "archived" and self._status_filter != "status:archived":
                continue

            filtered.append(entry)

        self._filtered_projects = filtered
        self._subtitle_label.setText(f"管理和追踪您的压铸项目，共 {len(filtered)} 个项目")
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        # 创建一个新的容器 Widget 来替换旧的
        new_container = QWidget()
        # 必须设置透明背景，否则可能会遮挡
        new_container.setStyleSheet("background: transparent;")
        
        layout = None
        if self._view_mode == "grid":
            layout = QGridLayout(new_container)
            layout.setContentsMargins(0, 0, 0, 0) # 避免双重 padding
            layout.setSpacing(24)
            cols = 3
            for idx, entry in enumerate(self._filtered_projects):
                card = ProjectCard(entry, parent=new_container)
                card.openRequested.connect(self._open_project)
                card.pinToggled.connect(self._pin_project)
                card.manageRequested.connect(self._manage_project)
                layout.addWidget(card, idx // cols, idx % cols)
            # 底部弹簧，确保内容靠上
            layout.setRowStretch((len(self._filtered_projects) // cols) + 1, 1)
            
        elif self._view_mode == "list":
            layout = QVBoxLayout(new_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
            for entry in self._filtered_projects:
                card = ProjectCard(entry, ProjectCardOptions(compact=True), parent=new_container)
                card.openRequested.connect(self._open_project)
                card.pinToggled.connect(self._pin_project)
                card.manageRequested.connect(self._manage_project)
                layout.addWidget(card)
            layout.addStretch()
            
        elif self._view_mode == "timeline":
            layout = QVBoxLayout(new_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
            groups: dict[str, list[ProjectEntry]] = {}
            for entry in self._filtered_projects:
                key = entry.project.create_time.strftime("%Y-%m")
                groups.setdefault(key, []).append(entry)
            
            for key in sorted(groups.keys(), reverse=True):
                header = SubtitleLabel(key, new_container)
                header.setStyleSheet(f"color: {COLORS['primary']}; font-weight: bold; margin-top: 12px;")
                layout.addWidget(header)
                for entry in groups[key]:
                    card = ProjectCard(entry, ProjectCardOptions(compact=True), parent=new_container)
                    card.openRequested.connect(self._open_project)
                    card.pinToggled.connect(self._pin_project)
                    card.manageRequested.connect(self._manage_project)
                    layout.addWidget(card)
            layout.addStretch()

        # 替换 ScrollArea 中的 Widget
        self._scroll.setWidget(new_container)
        self._grid_container = new_container

    def _update_index_status(self, enabled: bool):
        self._sidebar.index_status.setText("索引已启用" if enabled else "普通模式")
        self._sidebar.index_status.setStyleSheet(f"color: {COLORS['success'] if enabled else COLORS['warning']}; font-size: 11px;")

    # --- Events ---

    def _on_nav_changed(self, key: str):
        self._status_filter = key
        self._title_label.setText({
            "all": "全部项目",
            "pinned": "置顶项目",
            "status:ongoing": "进行中项目",
            "status:delivered": "已交付项目",
            "status:archived": "归档项目"
        }.get(key, "项目列表"))
        self._apply_filter()

    def _on_search_changed(self, text: str):
        self._search_query = text
        self._apply_filter()

    def _on_view_changed(self, mode: str):
        self._view_mode = mode
        self._rebuild_grid()

    def _on_action_triggered(self, action: str):
        if action == "create":
            self._open_create_project()
        elif action == "rebuild":
            self._rebuild_index()
        elif action == "pick_lib":
            self._pick_library_root()

    def _on_tag_selected(self, tag: str):
        # 简单实现：点击搜索框填入
        self._right_panel.search_box.setText(tag)

    def _reset_filters(self):
        self._status_filter = "all"
        self._search_query = ""
        self._right_panel.search_box.clear()
        self._apply_filter()

    # --- Actions (Reuse existing logic) ---
    def _pick_library_root(self):
        path = QFileDialog.getExistingDirectory(self, "选择压铸项目库根目录", self._library_root or "")
        if not path: return
        self._library_root = path
        save_user_config(UserConfig(library_root=path))
        self._sidebar.index_status.setText("加载中...")
        self._reload_projects()

    def _rebuild_index(self):
        if not self._library_root: return
        try:
            db = rebuild_index(Path(self._library_root), include_archived=True)
            self._update_index_status(db.fts5_enabled)
            self._reload_projects()
            QMessageBox.information(self, "成功", "索引重建完成")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))

    def _open_create_project(self):
        if not self._library_root:
            QMessageBox.warning(self, "提示", "请先在右侧选择库")
            return
        dlg = _CreateProjectDialog(self)
        if dlg.exec(): # MessageBoxBase uses standard exec but returns boolean or result, checking standard way
            try:
                from dcpm.services.project_service import create_project
                res = create_project(Path(self._library_root), dlg.build_request())
                try: upsert_one_project(Path(self._library_root), ProjectEntry(project=res.project, project_dir=res.project_dir))
                except: pass
                self._reload_projects()
            except Exception as e:
                QMessageBox.critical(self, "错误", str(e))

    def _open_project(self, entry: ProjectEntry):
        if not self._library_root: return
        try: mark_opened_now(Path(self._library_root), entry.project.id)
        except: pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.project_dir)))
        self._reload_projects()

    def _pin_project(self, pid: str, pinned: bool):
        if not self._library_root: return
        toggle_pinned(Path(self._library_root), pid, pinned)
        self._reload_projects() # Refresh to update UI

    def _manage_project(self, entry: ProjectEntry):
        dlg = _ManageProjectDialog(entry, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                from dcpm.services.project_service import archive_project, unarchive_project, edit_project_metadata
                
                # Logic same as before
                if dlg.is_pinned != entry.pinned:
                    toggle_pinned(Path(self._library_root), entry.project.id, dlg.is_pinned)
                
                desired = dlg.status
                is_archived_dir = "归档项目" in Path(entry.project_dir).parts
                root = Path(self._library_root)
                
                if desired == "archived" and not is_archived_dir:
                    res = archive_project(root, Path(entry.project_dir))
                    upsert_one_project(root, ProjectEntry(project=res.project, project_dir=res.project_dir, pinned=dlg.is_pinned))
                elif desired != "archived" and is_archived_dir:
                    res = unarchive_project(root, Path(entry.project_dir), status=desired)
                    upsert_one_project(root, ProjectEntry(project=res.project, project_dir=res.project_dir, pinned=dlg.is_pinned))
                else:
                    updated = edit_project_metadata(Path(entry.project_dir), tags=dlg.tags_list, status=desired, description=dlg.description)
                    upsert_one_project(root, ProjectEntry(project=updated, project_dir=Path(entry.project_dir), pinned=dlg.is_pinned))
                self._reload_projects()
            except Exception as e:
                QMessageBox.critical(self, "错误", str(e))


from qfluentwidgets import (
    BodyLabel, CardWidget, SegmentedWidget, SubtitleLabel,
    FluentIcon as FI, IconWidget, MessageBoxBase, LineEdit, 
    StrongBodyLabel, PrimaryPushButton, PushButton
)

class _CreateProjectDialog(MessageBoxBase):
    """Fluent 风格的新建项目对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("新建项目", self)
        
        # 字段容器
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)
        
        # 月份
        self.monthLabel = StrongBodyLabel("月份 (YYYY-MM)", self)
        self.monthEdit = LineEdit(self)
        self.monthEdit.setText(datetime.now().strftime("%Y-%m"))
        self.monthEdit.setPlaceholderText("例如: 2024-03")
        self.viewLayout.addWidget(self.monthLabel)
        self.viewLayout.addWidget(self.monthEdit)
        self.viewLayout.addSpacing(12)
        
        # 客户
        self.custLabel = StrongBodyLabel("客户名称", self)
        self.custEdit = LineEdit(self)
        self.custEdit.setPlaceholderText("例如: BMW, Tesla")
        self.viewLayout.addWidget(self.custLabel)
        self.viewLayout.addWidget(self.custEdit)
        self.viewLayout.addSpacing(12)
        
        # 项目名称
        self.nameLabel = StrongBodyLabel("项目名称", self)
        self.nameEdit = LineEdit(self)
        self.nameEdit.setPlaceholderText("输入项目名称")
        self.viewLayout.addWidget(self.nameLabel)
        self.viewLayout.addWidget(self.nameEdit)
        self.viewLayout.addSpacing(12)
        
        # 标签
        self.tagsLabel = StrongBodyLabel("标签 (可选)", self)
        self.tagsEdit = LineEdit(self)
        self.tagsEdit.setPlaceholderText("用逗号分隔，如: 压铸, 模具")
        self.viewLayout.addWidget(self.tagsLabel)
        self.viewLayout.addWidget(self.tagsEdit)
        
        # 调整按钮文字
        self.yesButton.setText("创建项目")
        self.cancelButton.setText("取消")
        
        # 简单的验证逻辑
        self.widget.setMinimumWidth(360)
        self.yesButton.setDisabled(True)
        self.custEdit.textChanged.connect(self._validate)
        self.nameEdit.textChanged.connect(self._validate)
        self.monthEdit.textChanged.connect(self._validate)

    def _validate(self):
        valid = bool(self.custEdit.text().strip() and 
                     self.nameEdit.text().strip() and 
                     self.monthEdit.text().strip())
        self.yesButton.setDisabled(not valid)

    def build_request(self):
        from dcpm.services.project_service import CreateProjectRequest
        return CreateProjectRequest(
            month=self.monthEdit.text(),
            customer=self.custEdit.text(),
            name=self.nameEdit.text(),
            tags=self.tagsEdit.text().split(",")
        )

class _ManageProjectDialog(QDialog):
    def __init__(self, entry: ProjectEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("管理项目")
        self.setFixedSize(500, 400)
        self.setStyleSheet(f"background: {COLORS['card']};")
        layout = QVBoxLayout(self)
        
        self._status_combo = QComboBox()
        self._status_combo.addItems(["ongoing", "delivered", "archived"])
        self._status_combo.setCurrentText(entry.project.status)
        
        self._pinned_check = QCheckBox("置顶")
        self._pinned_check.setChecked(entry.pinned)
        
        self._tags_edit = QLineEdit(",".join(entry.project.tags))
        self._desc_edit = QPlainTextEdit(entry.project.description)
        
        form = QFormLayout()
        form.addRow("状态", self._status_combo)
        form.addRow("", self._pinned_check)
        form.addRow("标签", self._tags_edit)
        form.addRow("备注", self._desc_edit)
        layout.addLayout(form)
        
        ok = QPushButton("保存")
        ok.clicked.connect(self.accept)
        layout.addWidget(ok)
    
    @property
    def status(self): return self._status_combo.currentText()
    @property
    def is_pinned(self): return self._pinned_check.isChecked()
    @property
    def tags_list(self): return self._tags_edit.text().split(",")
    @property
    def description(self): return self._desc_edit.toPlainText()
