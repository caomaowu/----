from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer, QEvent, QRectF
from PyQt6.QtGui import QDesktopServices, QFont, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget, QStackedWidget
)
from qfluentwidgets import (
    BodyLabel, CardWidget, SegmentedWidget, SubtitleLabel,
    FluentIcon as FI, IconWidget
)

from dcpm.ui.theme.colors import APP_BG, COLORS
from dcpm.ui.views.file_browser import FileBrowser
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
from dcpm.ui.views.settings_interface import SettingsInterface


from dcpm.ui.components.note_dialog import NoteDialog
from dcpm.services.note_service import NoteService

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
        
        # Init Note Service if library root is available
        self._note_service = NoteService(Path(self._library_root)) if self._library_root else None

        self._reload_projects()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() != QEvent.Type.WindowStateChange:
            return
        if getattr(self, "_view_mode", None) != "grid":
            return
        if not hasattr(self, "_stack"):
            return
        if self._stack.currentIndex() != 0:
            return
        QTimer.singleShot(0, self._rebuild_grid)

    def _build_main_content(self) -> QWidget:
        self._stack = QStackedWidget()
        
        # --- Page 1: Project List ---
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
        self._view_switch = Pivot()
        self._view_switch.addItem("grid", "⊞ 网格", lambda: self._on_view_changed("grid"))
        self._view_switch.addItem("list", "☰ 列表", lambda: self._on_view_changed("list"))
        self._view_switch.addItem("timeline", "◷ 时间线", lambda: self._on_view_changed("timeline"))
        self._view_switch.setCurrentItem("grid")
        header_layout.addWidget(self._view_switch, 0, Qt.AlignmentFlag.AlignBottom) # Align to bottom to look good

        layout.addLayout(header_layout)

        # Stats Bar
        self._stats_layout = QHBoxLayout()
        self._stats_layout.setSpacing(20)
        # Placeholders
        for _ in range(4):
            self._stats_layout.addWidget(StatCard("-", "0", "-", COLORS["secondary"], 0))
        layout.addLayout(self._stats_layout)

        # Filter Bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)

        # 状态筛选下拉
        self._status_btn = DropDownPushButton("📁 全部状态", self)
        self._status_btn.setFixedHeight(40)
        status_menu = RoundMenu(parent=self._status_btn)
        status_menu.addActions([
            Action("全部状态", triggered=lambda: self._set_filter("status", "all")),
            Action("进行中", triggered=lambda: self._set_filter("status", "ongoing")),
            Action("已交付", triggered=lambda: self._set_filter("status", "delivered")),
            Action("已归档", triggered=lambda: self._set_filter("status", "archived")),
        ])
        self._status_btn.setMenu(status_menu)
        filter_layout.addWidget(self._status_btn)

        # 时间筛选下拉
        self._time_btn = DropDownPushButton("📅 全部时间", self)
        self._time_btn.setFixedHeight(40)
        # 菜单内容在 _update_filter_menus 中动态生成
        self._time_menu = RoundMenu(parent=self._time_btn)
        self._time_btn.setMenu(self._time_menu)
        filter_layout.addWidget(self._time_btn)

        # 标签筛选下拉
        self._tag_btn = DropDownPushButton("🏷️ 全部标签", self)
        self._tag_btn.setFixedHeight(40)
        self._tag_menu = RoundMenu(parent=self._tag_btn)
        self._tag_btn.setMenu(self._tag_menu)
        filter_layout.addWidget(self._tag_btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Project Scroll Area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_container = QWidget()
        # 初始给一个空 layout，防止 _rebuild_grid 前的空白期
        QVBoxLayout(self._grid_container).setContentsMargins(0, 0, 0, 0)

        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll)

        self._stack.addWidget(container)

        # --- Page 2: File Browser ---
        self._file_browser = FileBrowser(self._library_root)
        self._file_browser.backRequested.connect(self._on_file_browser_back)
        self._stack.addWidget(self._file_browser)

        # --- Page 3: Settings ---
        self._settings_interface = SettingsInterface(self)
        self._stack.addWidget(self._settings_interface)

        return self._stack

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
        
        # Update Filter Menu (Time)
        self._time_menu.clear()
        self._time_menu.addAction(Action("全部时间", triggered=lambda: self._set_filter("time", "all")))
        for month, count in stats.month_counts[:12]: # Show recent 12 months
             self._time_menu.addAction(Action(f"{month} ({count})", triggered=lambda m=month: self._set_filter("time", m)))

        # Update Filter Menu (Tags)
        self._tag_menu.clear()
        self._tag_menu.addAction(Action("全部标签", triggered=lambda: self._set_filter("tag", "all")))
        for tag, count in stats.popular_tags[:20]:
            self._tag_menu.addAction(Action(f"{tag} ({count})", triggered=lambda t=tag: self._set_filter("tag", t)))

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
        except Exception as e:
            # Fallback for UI if DB fails, ensures panel is not empty
            self._right_panel.update_activities([])

    def _set_filter(self, type_: str, value: str):
        if type_ == "status":
            self._status_filter = "all" if value == "all" else f"status:{value}"
            self._status_btn.setText("📁 全部状态" if value == "all" else {
                "ongoing": "📁 进行中", "delivered": "📁 已交付", "archived": "📁 已归档"
            }.get(value, value))
        elif type_ == "time":
            self._time_filter = value
            self._time_btn.setText("📅 全部时间" if value == "all" else f"📅 {value}")
        elif type_ == "tag":
            # For now single tag filter logic needs implementation in _apply_filter
            # Currently _status_filter handles "status:" and "month:" prefix.
            # Let's generalize.
            self._tag_filter = value # We need to add this attribute
            self._tag_btn.setText("🏷️ 全部标签" if value == "all" else f"🏷️ {value}")
            
        self._apply_filter()

    def _apply_filter(self) -> None:
        q = self._search_query.lower()
        filtered = []

        for entry in self._all_projects:
            # 1. Status / Nav Filter (Sidebar logic)
            if self._status_filter != "all":
                if self._status_filter == "pinned":
                    if not entry.pinned: continue
                elif self._status_filter.startswith("status:"):
                    status = self._status_filter.split(":")[1]
                    if entry.project.status != status: continue
                elif self._status_filter.startswith("month:"):
                    month = self._status_filter.split(":")[1]
                    if entry.project.create_time.strftime("%Y-%m") != month: continue

            # 2. Top Bar Filters (Time & Tag)
            if self._time_filter != "all":
                 if entry.project.create_time.strftime("%Y-%m") != self._time_filter:
                     continue
            
            if hasattr(self, "_tag_filter") and self._tag_filter != "all":
                if self._tag_filter not in entry.project.tags:
                    continue

            # 3. Search Query
            if q:
                text = f"{entry.project.id} {entry.project.name} {entry.project.customer} {' '.join(entry.project.tags)}".lower()
                if q not in text:
                    continue

            # 4. Archive Hiding (default hidden unless viewing archived)
            # If user explicitly selected archived via status filter, show it.
            # If user selected a specific time/tag, maybe show archived? 
            # Let's keep simple: if not explicitly asking for archived status, hide archived projects.
            if entry.project.status == "archived":
                # Show if status filter is explicitly archived
                if self._status_filter != "status:archived":
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
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(1, 1)
            layout.setColumnStretch(2, 1)
            for idx, entry in enumerate(self._filtered_projects):
                card = ProjectCard(entry, parent=new_container)
                card.openRequested.connect(self._open_project)
                card.pinToggled.connect(self._pin_project)
                card.manageRequested.connect(self._manage_project)
                card.deleteRequested.connect(self._prompt_delete_project)
                card.noteRequested.connect(self._open_project_note)
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
                card.deleteRequested.connect(self._prompt_delete_project)
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
                    card.deleteRequested.connect(self._prompt_delete_project)
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
        if key == "settings":
            self._stack.setCurrentWidget(self._settings_interface)
            self._title_label.setText("系统设置")
            self._subtitle_label.setText("管理应用偏好和外部集成")
            # Hide filter controls when in settings
            # self._status_btn.setVisible(False) ... (Optional, but let's keep it simple for now)
            return

        # If coming back from settings or file browser, make sure we are on page 0
        if self._stack.currentWidget() != self._stack.widget(0):
            self._stack.setCurrentIndex(0)

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
            InfoBar.success(
                title='索引重建完成',
                content="本地索引数据库已成功更新",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )
        except Exception as e:
            InfoBar.error(
                title='失败',
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _open_create_project(self):
        if not self._library_root:
            InfoBar.warning(
                title='提示',
                content="请先在右侧选择库",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )
            return
        dlg = _CreateProjectDialog(self)
        if dlg.exec(): # MessageBoxBase uses standard exec but returns boolean or result, checking standard way
            try:
                from dcpm.services.project_service import create_project
                from dcpm.ui.views.settings_interface import ScanThread
                from dcpm.infra.config.user_config import load_user_config
                
                res = create_project(Path(self._library_root), dlg.build_request())
                try: upsert_one_project(Path(self._library_root), ProjectEntry(project=res.project, project_dir=res.project_dir))
                except: pass
                
                self._reload_projects()
                
                # Trigger incremental scan for the new project
                cfg = load_user_config()
                if cfg.shared_drive_path:
                    # We use a throw-away thread instance here, but we need to keep a reference to it
                    # or it might be garbage collected before finishing? QThread handles this usually if started.
                    # But safer to attach to self.
                    self._auto_scan_thread = ScanThread(
                        Path(self._library_root), 
                        cfg.shared_drive_path, 
                        target_project=res.project
                    )
                    # We don't need to block UI or show heavy notifications for this auto-scan
                    # Maybe just a small log or silent fail.
                    self._auto_scan_thread.start()
                    
            except Exception as e:
                InfoBar.error(
                    title='错误',
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )

    def _open_project(self, entry: ProjectEntry):
        if not self._library_root: return
        try: mark_opened_now(Path(self._library_root), entry.project.id)
        except: pass
        
        # Switch to File Browser view
        self._file_browser.set_root(entry.project_dir, f"{entry.project.id} ({entry.project.name})", entry.project.id)
        self._stack.setCurrentIndex(1)
        
        self._reload_projects()

    def _on_file_browser_back(self):
        self._stack.setCurrentIndex(0)

    def _pin_project(self, pid: str, pinned: bool):
        if not self._library_root: return
        toggle_pinned(Path(self._library_root), pid, pinned)
        self._reload_projects() # Refresh to update UI

    def _manage_project(self, entry: ProjectEntry):
        dlg = _ManageProjectDialog(entry, self)
        
        # 处理删除逻辑 - 现在复用 self._prompt_delete_project
        def _on_delete():
            if self._prompt_delete_project(entry):
                dlg.reject() # 如果删除成功，关闭弹窗

        dlg.deleteRequested.connect(_on_delete)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                from dcpm.services.project_service import (
                    archive_project,
                    clear_project_cover,
                    edit_project_metadata,
                    set_project_cover,
                    unarchive_project,
                )
                
                # Logic same as before
                if dlg.is_pinned != entry.pinned:
                    toggle_pinned(Path(self._library_root), entry.project.id, dlg.is_pinned)
                
                desired = dlg.status
                is_archived_dir = "归档项目" in Path(entry.project_dir).parts
                root = Path(self._library_root)
                
                final_dir = Path(entry.project_dir)
                final_project = entry.project

                if desired == "archived" and not is_archived_dir:
                    res = archive_project(root, Path(entry.project_dir))
                    final_dir = res.project_dir
                    final_project, final_dir = edit_project_metadata(final_dir, name=dlg.name, tags=dlg.tags_list, status=desired, description=dlg.description)
                elif desired != "archived" and is_archived_dir:
                    res = unarchive_project(root, Path(entry.project_dir), status=desired)
                    final_dir = res.project_dir
                    final_project, final_dir = edit_project_metadata(final_dir, name=dlg.name, tags=dlg.tags_list, status=desired, description=dlg.description)
                else:
                    final_project, final_dir = edit_project_metadata(final_dir, name=dlg.name, tags=dlg.tags_list, status=desired, description=dlg.description)

                if dlg.cover_cleared:
                    final_project = clear_project_cover(final_dir)
                elif dlg.cover_source_path:
                    final_project = set_project_cover(final_dir, dlg.cover_source_path)

                upsert_one_project(root, ProjectEntry(project=final_project, project_dir=final_dir, pinned=dlg.is_pinned))
                self._reload_projects()
                
                # Check if core info changed to trigger incremental scan
                core_changed = (
                    final_project.name != entry.project.name or
                    final_project.customer_code != entry.project.customer_code or
                    final_project.part_number != entry.project.part_number
                )
                
                if core_changed:
                    # Trigger incremental scan to update matching scores
                    from dcpm.ui.views.settings_interface import ScanThread
                    from dcpm.infra.config.user_config import load_user_config
                    
                    cfg = load_user_config()
                    if cfg.shared_drive_path:
                        self._auto_scan_thread = ScanThread(
                            Path(self._library_root), 
                            cfg.shared_drive_path, 
                            target_project=final_project
                        )
                        self._auto_scan_thread.start()
                        
            except Exception as e:
                InfoBar.error(
                    title='错误',
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )

    def _open_project_note(self, entry: ProjectEntry):
        if not self._note_service:
            return

        project_dir = entry.project_dir
        current_note = self._note_service.get_note(project_dir) or ""
        
        w = NoteDialog(f"项目留言: {entry.project.name}", current_note, self)
        if w.exec():
            text = w.get_text()
            self._note_service.save_note(project_dir, text)
            
            InfoBar.success(
                title='保存成功',
                content="项目备注已更新",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

    def _prompt_delete_project(self, entry: ProjectEntry) -> bool:
        """弹出删除确认框，如果确认则执行删除。返回 True 表示已删除。"""
        title = "确认删除"
        content = f"确定要彻底删除项目 {entry.project.name} 吗？\n\n此操作将永久删除项目文件夹及其所有内容，且不可恢复！"
        w = MessageBoxBase(self)
        w.titleLabel = SubtitleLabel(title, w)
        w.viewLayout.addWidget(w.titleLabel)
        w.viewLayout.addWidget(BodyLabel(content, w))
        w.yesButton.setText("确认删除")
        w.cancelButton.setText("取消")
        w.yesButton.setStyleSheet("QPushButton { background-color: #dc2626; color: white; border: none; } QPushButton:hover { background-color: #b91c1c; }")
        
        if w.exec():
            try:
                from dcpm.services.project_service import delete_project_physically
                from dcpm.services.index_service import delete_project_index
                
                # 1. 删除索引
                delete_project_index(Path(self._library_root), entry.project.id)
                # 2. 删除物理文件
                delete_project_physically(entry.project_dir)
                
                self._reload_projects()
                InfoBar.success(
                    title='项目已删除',
                    content=f"项目 {entry.project.name} 已彻底移除",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
                return True
            except Exception as e:
                InfoBar.error(
                    title='删除失败',
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )
                return False
        return False


from qfluentwidgets import (
    BodyLabel, CardWidget, SegmentedWidget, SubtitleLabel,
    FluentIcon as FI, IconWidget, MessageBoxBase, LineEdit, 
    StrongBodyLabel, PrimaryPushButton, PushButton,
    DropDownPushButton, RoundMenu, Action, InfoBar, InfoBarPosition,
    Pivot
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
    deleteRequested = pyqtSignal()

    def __init__(self, entry: ProjectEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("管理项目")
        self.setFixedSize(500, 450) # Increased height
        self.setStyleSheet(f"background: {COLORS['card']};")
        layout = QVBoxLayout(self)
        
        self._status_combo = QComboBox()
        self._status_combo.addItems(["ongoing", "delivered", "archived"])
        self._status_combo.setCurrentText(entry.project.status)
        
        self._pinned_check = QCheckBox("置顶")
        self._pinned_check.setChecked(entry.pinned)
        
        self._name_edit = LineEdit()
        self._name_edit.setText(entry.project.name)

        self._tags_edit = LineEdit()
        self._tags_edit.setText(",".join(entry.project.tags))
        self._desc_edit = QPlainTextEdit(entry.project.description or "")

        self._cover_source_path: str | None = None
        self._cover_cleared = False
        self._cover_preview = QLabel()
        self._cover_preview.setFixedSize(180, 100)
        self._cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_preview.setStyleSheet(
            f"background: {COLORS['bg']}; border: 1px solid {COLORS['border']}; border-radius: 10px;"
        )
        self._cover_preview.setText("无封面")
        self._apply_existing_cover(entry)
        cover_pick_btn = PushButton("选择图片…")
        cover_pick_btn.clicked.connect(self._pick_cover)
        cover_clear_btn = PushButton("清除封面")
        cover_clear_btn.clicked.connect(self._clear_cover)

        cover_widget = QWidget()
        cover_layout = QHBoxLayout(cover_widget)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setSpacing(12)
        cover_layout.addWidget(self._cover_preview)
        cover_btn_col = QVBoxLayout()
        cover_btn_col.setContentsMargins(0, 0, 0, 0)
        cover_btn_col.setSpacing(8)
        cover_btn_col.addWidget(cover_pick_btn)
        cover_btn_col.addWidget(cover_clear_btn)
        cover_btn_col.addStretch()
        cover_layout.addLayout(cover_btn_col)
        
        form = QFormLayout()
        form.addRow("名称", self._name_edit)
        form.addRow("状态", self._status_combo)
        form.addRow("", self._pinned_check)
        form.addRow("封面", cover_widget)
        form.addRow("标签", self._tags_edit)
        form.addRow("备注", self._desc_edit)
        layout.addLayout(form)
        
        # Buttons Layout
        btn_layout = QHBoxLayout()
        
        # Delete Button (Red)
        del_btn = PushButton("🗑️ 删除项目")
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2;
                color: #dc2626;
                border: 1px solid #fecaca;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #fecaca;
            }
            QPushButton:pressed {
                background-color: #fca5a5;
            }
        """)
        del_btn.clicked.connect(self.deleteRequested.emit)
        btn_layout.addWidget(del_btn)
        
        btn_layout.addStretch()
        
        ok = PrimaryPushButton("保存")
        ok.clicked.connect(self.accept)
        btn_layout.addWidget(ok)
        
        layout.addLayout(btn_layout)

    def _rounded_pixmap(self, pixmap: QPixmap, w: int, h: int, radius: int) -> QPixmap:
        target = QPixmap(w, h)
        target.fill(Qt.GlobalColor.transparent)

        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        painter.setClipPath(path)

        scaled = pixmap.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = int((w - scaled.width()) / 2)
        y = int((h - scaled.height()) / 2)
        painter.drawPixmap(x, y, scaled)
        painter.end()
        return target

    def _set_cover_preview_from_file(self, file_path: str) -> None:
        pix = QPixmap(file_path)
        if pix.isNull():
            self._cover_preview.setPixmap(QPixmap())
            self._cover_preview.setText("无法预览")
            return
        self._cover_preview.setText("")
        self._cover_preview.setPixmap(self._rounded_pixmap(pix, 180, 100, 10))

    def _apply_existing_cover(self, entry: ProjectEntry) -> None:
        cover = entry.project.cover_image
        if not cover:
            return
        p = Path(cover)
        if not p.is_absolute():
            p = Path(entry.project_dir) / p
        if p.exists() and p.is_file():
            self._set_cover_preview_from_file(str(p))

    def _pick_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择封面图片",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All Files (*.*)",
        )
        if not path:
            return
        self._cover_source_path = path
        self._cover_cleared = False
        self._set_cover_preview_from_file(path)

    def _clear_cover(self) -> None:
        self._cover_source_path = None
        self._cover_cleared = True
        self._cover_preview.setPixmap(QPixmap())
        self._cover_preview.setText("无封面")
    
    @property
    def status(self): return self._status_combo.currentText()
    @property
    def is_pinned(self): return self._pinned_check.isChecked()
    @property
    def name(self): return self._name_edit.text().strip()
    @property
    def tags_list(self): return self._tags_edit.text().split(",")
    @property
    def description(self): return self._desc_edit.toPlainText()
    @property
    def cover_source_path(self): return self._cover_source_path
    @property
    def cover_cleared(self): return self._cover_cleared
