"""
Event handling for all possible events this plugin may handle.
"""

import os
from typing import Optional, TYPE_CHECKING
from datetime import timedelta

from octoprint.util import get_formatted_timedelta

from .print_state import PrintState
from .pushover import Pushover, Priority

if TYPE_CHECKING:
    from .plugin import PushoverPlugin


class EventHandlers:
    """
    Contains event handlers for all possible events this plugin may handle.
    """

    # pylint: disable=protected-access,missing-function-docstring

    def __init__(self, plugin: "PushoverPlugin"):
        self.plugin = plugin

    @property
    def print_session(self) -> Optional[PrintState]:
        return self.plugin.print_session

    @property
    def pushover(self) -> Optional[Pushover]:
        return self.plugin.pushover

    def on_system_startup(self, _payload):
        pushover = self.pushover
        if pushover is None:
            return

        priority = self.plugin._settings.get(["events", "Startup", "priority"])
        if priority is None or priority == 0:
            return

        self.plugin.executor.submit(
            self.pushover.send_message,
            self,
            message=self.plugin._settings.get(["events", "Startup", "message"]),
            priority=Priority(int(priority)),
        )

    def on_system_shutdown(self, _payload):
        pushover = self.pushover
        if pushover is None:
            return

        priority = self.plugin._settings.get(["events", "Shutdown", "priority"])
        if priority is None or priority == 0:
            return

        self.plugin.executor.submit(
            self.pushover.send_message,
            self,
            message=self.plugin._settings.get(["events", "Shutdown", "message"]),
            priority=Priority(int(priority)),
        )

    def on_system_error(self, payload):
        if not self.print_session.is_printing:
            return

        pushover = self.pushover
        if pushover is None:
            return

        priority = self.plugin._settings.get(["events", "Error", "priority"])
        if priority is None or priority == 0:
            return

        self.plugin.executor.submit(
            self.pushover.send_message,
            self,
            message=self.plugin._settings.get(["events", "Error", "message"]).format(
                error=payload["error"]
            ),
            priority=Priority(int(priority)),
        )

    def on_print_done(self, payload):
        self.print_session.on_print_done()

        pushover = self.pushover
        if pushover is None:
            return

        priority = self.plugin._settings.get(["events", "PrintDone", "priority"])
        if priority is None or priority == 0:
            return

        self.plugin.executor.submit(
            self.pushover.send_message,
            self,
            message=self.plugin._settings.get(
                ["events", "PrintDone", "message"]
            ).format(
                file=os.path.basename(payload["name"]),
                elapsed_time=get_formatted_timedelta(
                    timedelta(seconds=payload["time"])
                ),
            ),
            priority=Priority(int(priority)),
        )

    def on_print_failed(self, payload):
        self.print_session.on_print_failed()

        pushover = self.pushover
        if pushover is None:
            return

        priority = self.plugin._settings.get(["events", "PrintFailed", "priority"])
        if priority is None or priority == 0:
            return

        self.plugin.executor.submit(
            self.pushover.send_message,
            self,
            message=self.plugin._settings.get(
                ["events", "PrintFailed", "message"]
            ).format(
                file=os.path.basename(payload["name"]),
            ),
            priority=Priority(int(priority)),
        )

    def on_filament_change(self, _payload):
        pushover = self.pushover
        if pushover is None:
            return

        priority = self.plugin._settings.get(["events", "FilamentChange", "priority"])
        if priority is None or priority == 0:
            return

        self.plugin.executor.submit(
            self.pushover.send_message,
            self,
            message=self.plugin._settings.get(
                ["events", "FilamentChange", "message"]
            ).format(
                m70_cmd=f"{self.print_session.m70_cmd})",
            ),
            priority=Priority(int(priority)),
        )

    def on_print_paused(self, _payload):
        pushover = self.pushover
        if pushover is None:
            return

        priority = self.plugin._settings.get(["events", "PrintPaused", "priority"])
        if priority is None or priority == 0:
            return

        self.plugin.executor.submit(
            self.pushover.send_message,
            self,
            message=self.plugin._settings.get(
                ["events", "PrintPaused", "message"]
            ).format(
                m70_cmd=f"{self.print_session.m70_cmd})",
            ),
            priority=Priority(int(priority)),
        )

    def on_print_waiting(self, payload):
        self.on_print_paused(payload)

    def on_print_z_change(self, payload):
        self.print_session.on_print_z_change(payload)

        if self.plugin.pushover is None:
            return

        if not self.print_session.is_printing:
            return

        priority = self.plugin._settings.get(["events", "PrintPaused", "priority"])
        if priority is None or priority == 0:
            return

        self.plugin.executor.submit(
            self.pushover.send_message,
            self,
            message=self.plugin._settings.get(
                ["events", "PrintPaused", "message"]
            ).format(
                m70_cmd=f"{self.print_session.m70_cmd})",
            ),
            priority=Priority(int(priority)),
        )
