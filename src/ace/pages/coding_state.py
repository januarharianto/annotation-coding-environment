"""Shared state for the coding page."""

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from ace.models.assignment import get_assignments_for_coder
from ace.models.codebook import list_codes
from ace.services.undo import UndoManager


@dataclass
class CodingState:
    """Mutable state shared across coding page modules."""

    conn: sqlite3.Connection
    coder_id: str
    sources: list
    assignments: list
    codes: list
    codes_by_id: dict = field(default_factory=dict)
    current_index: int = 0
    pending_selection: dict | None = None
    undo_mgr: UndoManager = field(default_factory=UndoManager)

    # UI refreshable references (set after UI is built)
    code_list_refresh: Any = None
    source_header_refresh: Any = None
    bottom_bar_refresh: Any = None
    annotation_list_refresh: Any = None
    text_container: Any = None  # ui.html element

    def current_assignment(self):
        return self.assignments[self.current_index]

    def current_source_id(self):
        return self.current_assignment()["source_id"]

    def reload_assignments(self):
        fresh = get_assignments_for_coder(self.conn, self.coder_id)
        self.assignments.clear()
        self.assignments.extend(fresh)

    def refresh_codes(self):
        fresh = list_codes(self.conn)
        self.codes.clear()
        self.codes.extend(fresh)
        self.codes_by_id.clear()
        self.codes_by_id.update({c["id"]: c for c in self.codes})
