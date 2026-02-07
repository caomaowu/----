from __future__ import annotations

import os
from pathlib import Path
from typing import Set

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QMutex, QWaitCondition, QSize, Qt
from PyQt6.QtGui import QPixmap, QImage, QImageReader

class ThumbnailWorker(QThread):
    """Worker thread for generating thumbnails"""
    thumbnail_ready = pyqtSignal(str, QPixmap)
    
    def __init__(self):
        super().__init__()
        self._queue: list[str] = []
        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._running = True
        
    def add_task(self, path: str):
        self._mutex.lock()
        if path not in self._queue:
            self._queue.append(path)
            self._condition.wakeOne()
        self._mutex.unlock()
        
    def stop(self):
        self._running = False
        self._condition.wakeAll()
        self.wait()

    def run(self):
        while self._running:
            self._mutex.lock()
            if not self._queue:
                self._condition.wait(self._mutex)
            
            if not self._running:
                self._mutex.unlock()
                break
                
            path = self._queue.pop(0) if self._queue else None
            self._mutex.unlock()
            
            if path:
                self._generate_thumbnail(path)

    def _generate_thumbnail(self, path: str):
        if not os.path.exists(path):
            return

        try:
            # Use QImageReader for better performance (can scale on load)
            reader = QImageReader(path)
            
            # Check if format is supported
            if not reader.canRead():
                return
                
            # Scale efficiently: Target roughly 200x200 for thumbnail
            target_size = QSize(200, 200)
            
            # Calculate scaled size preserving aspect ratio
            orig_size = reader.size()
            if not orig_size.isValid():
                return
                
            reader.setScaledSize(orig_size.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio))
            
            img = reader.read()
            if not img.isNull():
                pixmap = QPixmap.fromImage(img)
                self.thumbnail_ready.emit(path, pixmap)
                
        except Exception as e:
            print(f"Error generating thumbnail for {path}: {e}")

class ThumbnailService(QObject):
    """Service to manage thumbnail generation and caching"""
    thumbnailLoaded = pyqtSignal(str, QPixmap)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: dict[str, QPixmap] = {}
        self._pending: Set[str] = set()
        
        # Start worker thread
        self._worker = ThumbnailWorker()
        self._worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._worker.start()
        
    def get_thumbnail(self, path: str) -> QPixmap | None:
        """Get cached thumbnail if available, otherwise return None and queue generation"""
        if path in self._cache:
            return self._cache[path]
            
        if self._is_image(path) and path not in self._pending:
            self._pending.add(path)
            self._worker.add_task(path)
            
        return None
        
    def _on_thumbnail_ready(self, path: str, pixmap: QPixmap):
        if path in self._pending:
            self._pending.remove(path)
        
        self._cache[path] = pixmap
        self.thumbnailLoaded.emit(path, pixmap)
        
    def _is_image(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.ico', '.tiff']

    def shutdown(self):
        self._worker.stop()
