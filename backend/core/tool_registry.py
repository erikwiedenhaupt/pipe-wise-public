# core/tool_registry.py
from __future__ import annotations
from typing import Optional, Dict, List
import threading
import logging

from . import models
from .storage import Storage

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ToolRegistry:
    def __init__(self, storage: Optional[Storage] = None):
        self._tools: Dict[str, models.ToolSpec] = {}
        self._lock = threading.RLock()
        self.storage = storage
        if self.storage:
            try:
                self._load_from_storage()
            except Exception:
                logger.exception("Failed to load tools from storage during init")

    def _load_from_storage(self):
        if not self.storage:
            return
        try:
            for spec in self.storage.list_tools():
                self._tools[spec.id] = spec
        except Exception:
            logger.exception("Error loading tools from storage")

    def register(self, tool: models.ToolSpec, persist: bool = True) -> None:
        with self._lock:
            self._tools[tool.id] = tool
            if persist and self.storage:
                try:
                    self.storage.register_tool(tool)
                except Exception:
                    logger.exception("Failed to persist tool spec")

    def unregister(self, tool_id: str) -> bool:
        with self._lock:
            if tool_id in self._tools:
                del self._tools[tool_id]
                return True
            return False

    def get(self, tool_id: str) -> Optional[models.ToolSpec]:
        with self._lock:
            if tool_id in self._tools:
                return self._tools[tool_id]
            if self.storage:
                try:
                    tool = self.storage.get_tool(tool_id)
                    if tool:
                        self._tools[tool.id] = tool
                        return tool
                except Exception:
                    logger.exception("Failed to fetch tool from storage")
            return None

    def list(self) -> List[models.ToolSpec]:
        with self._lock:
            return list(self._tools.values())