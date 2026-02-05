from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QMainWindow, QStackedWidget, QWidget
)

from dcpm.ui.theme.colors import APP_BG, COLORS
from dcpm.ui.views.file_browser import FileBrowser
from dcpm.infra.config.user_config import UserConfig, load_user_config, save_user_config
from dcpm.services.library_service import ProjectEntry
from dcpm.services.index_service import (
    DashboardStats,
    get_recent_activity,
    mark_opened_now,
)

from dcpm.ui.views.sidebar import SidebarWidget
from dcpm.ui.views.right_panel import RightPanel
from dcpm.ui.views.settings_interface import SettingsInterface
from dcpm.ui.views.dashboard import DashboardView

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

        # 1. Sidebar
        self._sidebar = SidebarWidget(self)
        self._sidebar.navChanged.connect(self._on_nav_changed)
        layout.addWidget(self._sidebar)

        # 2. Main Content (Stacked)
        self._stack = QStackedWidget()
        
        # --- Page 1: Dashboard ---
        self._dashboard = DashboardView(self._library_root)
        self._dashboard.projectOpened.connect(self._on_project_opened)
        self._dashboard.dataLoaded.connect(self._on_dashboard_data_loaded)
        self._dashboard.indexRebuilt.connect(self._on_index_rebuilt)
        self._stack.addWidget(self._dashboard)

        # --- Page 2: File Browser ---
        self._file_browser = FileBrowser(self._library_root)
        self._file_browser.backRequested.connect(self._on_file_browser_back)
        self._stack.addWidget(self._file_browser)

        # --- Page 3: Settings ---
        self._settings_interface = SettingsInterface(self)
        self._stack.addWidget(self._settings_interface)

        layout.addWidget(self._stack, 1)  # Stretch

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"background-color: {COLORS['border']};")
        line.setFixedWidth(1)
        layout.addWidget(line)

        # 3. Right Panel
        self._right_panel = RightPanel(self)
        self._right_panel.searchChanged.connect(self._dashboard.set_search_query)
        self._right_panel.actionTriggered.connect(self._on_action_triggered)
        self._right_panel.tagSelected.connect(self._on_tag_selected)
        layout.addWidget(self._right_panel)
        
        # Initial Load
        QTimer.singleShot(0, self._dashboard.reload_projects)

    def changeEvent(self, event):
        super().changeEvent(event)
        # Forward window state changes if needed, but Dashboard handles its own layout updates now.
        pass

    # --- Events ---

    def _on_nav_changed(self, key: str):
        if key == "settings":
            self._stack.setCurrentWidget(self._settings_interface)
            return

        # If coming back from settings or file browser, make sure we are on page 0
        if self._stack.currentWidget() != self._stack.widget(0):
            self._stack.setCurrentIndex(0)

        self._dashboard.set_nav_filter(key)

    def _on_action_triggered(self, action: str):
        if action == "create":
            self._dashboard.open_create_project()
        elif action == "rebuild":
            self._dashboard.rebuild_index_action()
        elif action == "pick_lib":
            self._pick_library_root()

    def _on_tag_selected(self, tag: str):
        # 简单实现：点击搜索框填入
        self._right_panel.search_box.setText(tag)

    def _on_project_opened(self, entry: ProjectEntry):
        if not self._library_root: return
        try: mark_opened_now(Path(self._library_root), entry.project.id)
        except: pass
        
        # Switch to File Browser view
        self._file_browser.set_root(entry.project_dir, f"{entry.project.id} ({entry.project.name})", entry.project.id)
        self._stack.setCurrentIndex(1)
        
        # Refresh dashboard when coming back? Maybe later. For now just update stats.
        self._dashboard.reload_projects()

    def _on_file_browser_back(self):
        self._stack.setCurrentIndex(0)

    def _on_dashboard_data_loaded(self, stats: DashboardStats):
        self._update_sidebar_data(stats)
        self._update_right_panel_data(stats)

    def _on_index_rebuilt(self, enabled: bool):
        self._sidebar.index_status.setText("索引已启用" if enabled else "普通模式")
        self._sidebar.index_status.setStyleSheet(f"color: {COLORS['success'] if enabled else COLORS['warning']}; font-size: 11px;")

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
            from datetime import datetime
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
            self._right_panel.update_activities([])

    def _pick_library_root(self):
        path = QFileDialog.getExistingDirectory(self, "选择压铸项目库根目录", self._library_root or "")
        if not path: return
        self._library_root = path
        save_user_config(UserConfig(library_root=path))
        
        self._dashboard.set_library_root(path)
        self._file_browser.set_root(None) # Reset file browser
        
        self._sidebar.index_status.setText("加载中...")
