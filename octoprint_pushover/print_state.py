"""
Contains printing state information.
"""

from typing import TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from . import PushoverPlugin


class PrintState:
    """
    Contains printing state information.
    """

    def __init__(self, plugin: "PushoverPlugin"):
        self.plugin = plugin
        self.is_printing = False
        self.last_minute = 0
        self.last_progress = 0
        self.start_time = None
        self.m70_cmd = ""
        self.first_layer = True

    def on_print_done(self):
        """Sets the state for a new print."""

        self.is_printing = False
        self.last_minute = 0
        self.last_progress = 0
        self.start_time = None

    def on_print_failed(self):
        """Sets the state for failed print."""

        self.is_printing = False

    def on_print_z_change(self, payload):
        """Sets the state for Z-height changes."""

        # FUTURE: make the Z change setting changeable
        if payload["new"] < 2 or payload["old"] is None:
            return

        self.first_layer = False

    @property
    def minutes_since_started(self):
        """Returns the number of minutes elapsed from start_time."""

        if self.start_time is None:
            return None

        delta = datetime.now() - self.start_time
        return int(round(delta.total_seconds() / 60))
