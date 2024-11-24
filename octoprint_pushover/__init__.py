"""
Module entry point for Pushover notifications.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os
import json
from io import BytesIO
import datetime

import octoprint.util
import octoprint.plugin
from octoprint.util import RepeatedTimer

import flask
from flask_login import current_user
import requests
from requests.exceptions import HTTPError
from PIL import Image

__author__ = "Thijs Bekke <thijsbekke@gmail.com>, Raresh Nistor <raresh@nistor.email>"
__license__ = "GNU Affero General Public License http://www.gnu.org/licenses/agpl.html"
__copyright__ = "Released under terms of the AGPLv3 License"
__plugin_name__ = "Pushover"
__plugin_pythoncompat__ = ">=3.7,<4"


class PushoverPlugin(  # pylint: disable=too-many-ancestors
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.ProgressPlugin,
    octoprint.plugin.OctoPrintPlugin,
):
    """
    Plugin information.
    """

    api_url = "https://api.pushover.net/1"
    m70_cmd = ""
    printing = False
    start_time = None
    last_minute = 0
    last_progress = 0
    first_layer = False
    timer = None
    bed_sent = False
    e1_sent = False
    progress = 0
    emoji = {
        "rocket": "\U0001F680",
        "clock": "\U000023F0",
        "warning": "\U000026A0",
        "finish": "\U0001F3C1",
        "hooray": "\U0001F389",
        "error": "\U000026D4",
        "stop": "\U000025FC",
        "temp": "\U0001F321",
        "four_leaf_clover": "\U0001f340",
        "waving_hand_sign": "\U0001f44b",
    }

    def get_assets(self):
        return {"js": ["js/pushover.js"]}

    def get_api_commands(self):
        return {"test": ["api_key", "user_key"]}

    def on_api_command(self, command, data):
        if command == "test":

            if not data["api_key"]:
                data["api_key"] = self.get_token()

            # When we are testing the token, create a test notification
            payload = {
                "message": "".join(
                    ["pewpewpew!! OctoPrint works. ", self.emoji.get("rocket", "")]
                ),
                "token": data["api_key"],
                "user": data["user_key"],
            }

            # If there is a sound, include it in the payload
            if "sound" in data:
                payload["sound"] = data["sound"]

            if "image" in data:
                payload["image"] = data["image"]

            # Validate the user key and send a message
            try:
                self.validate_pushover(data["api_key"], data["user_key"])
                self.event_message(payload)
                return flask.jsonify({"success": True})
            except Exception as e:
                return flask.jsonify({"success": False, "msg": e.message})
        return flask.make_response("Unknown command", 400)

    def check_schedule(self):
        """
        Check the scheduler
        Send a notification
        """
        if not self.has_own_token():
            return

        scheduleMod = self._settings.get(["events", "Scheduled", "mod"])

        if (
            self.printing
            and scheduleMod
            and self.last_minute > 0
            and self.last_minute % int(scheduleMod) == 0
        ):

            self.event_message(
                {
                    "message": self._settings.get(
                        ["events", "Scheduled", "message"]
                    ).format(elapsed_time=self.last_minute),
                    "priority": self._settings.get(["events", "Scheduled", "priority"]),
                }
            )

    #
    # Meta
    #

    def get_update_information(self):
        return {
            "pushover": {
                "displayName": "Pushover Plugin",
                "displayVersion": self._plugin_version,
                "type": "github_release",
                "user": "thijsbekke",
                "repo": "OctoPrint-Pushover",
                "current": self._plugin_version,
                "pip": "https://github.com/thijsbekke/OctoPrint-Pushover/archive/{target_version}.zip",
            }
        }

    #
    # Event Hooks
    #

    def on_event(self, event, payload):
        if payload is None:
            payload = {}

        # StatusNotPrinting
        self._logger.debug("Got an event: %s, payload: %s" % (event, str(payload)))
        # It's easier to ask forgiveness than to ask permission.
        try:
            # Method exists, and was used.
            payload["message"] = getattr(self, event)(payload)

            self._logger.debug("Event triggered: %s " % str(event))
        except AttributeError:
            self._logger.debug(
                "event: %s has an AttributeError %s" % (event, str(payload))
            )
            # By default the message is simple and does not need any formatting
            payload["message"] = self._settings.get(["events", event, "message"])

        if payload["message"] is None:
            return

        # Does the event exists in the settings ? if not we don't want it
        if not event in self.get_settings_defaults()["events"]:
            return

        # Only continue when there is a priority
        priority = self._settings.get(["events", event, "priority"])

        # By default, messages have normal priority (a priority of 0).
        # We do not support the Emergency Priority (2) because there is no way of canceling it here,
        if priority:
            payload["priority"] = priority
            self.event_message(payload)

    def on_after_startup(self):
        """
        Valide settings on startup
        :return:
        """
        try:
            self.validate_pushover(self.get_token(), self._settings.get(["user_key"]))
        except Exception as e:
            self._logger.info(str(e))

        self.restart_timer()

    def on_print_progress(self, storage, path, progress):
        if not self.has_own_token():
            return

        progressMod = self._settings.get(["events", "Progress", "mod"])

        if (
            self.printing
            and progressMod
            and progress > 0
            and progress % int(progressMod) == 0
            and self.last_progress != progress
        ):
            self.last_progress = progress
            self.event_message(
                {
                    "message": self._settings.get(
                        ["events", "Progress", "message"]
                    ).format(percentage=progress),
                    "priority": self._settings.get(["events", "Scheduled", "priority"]),
                }
            )

    def sent_gcode(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
        """
        M70 Gcode commands are used for sending a text when print is paused
        :param comm_instance:
        :param phase:
        :param cmd:
        :param cmd_type:
        :param gcode:
        :param args:
        :param kwargs:
        :return:
        """

        if gcode and gcode != "G1":
            mss = self.get_mins_since_started()

            if self.last_minute != mss:
                self.last_minute = mss
                self.check_schedule()

        if gcode and gcode == "M600":
            self.on_event("FilamentChange", None)

        if gcode and gcode == "M70":
            self.m70_cmd = cmd[3:]

        if gcode and gcode == "M117" and cmd[4:].strip() != "":
            self.m70_cmd = cmd[4:]

    #
    # Event Handles
    #

    # Start with event handling: http://docs.octoprint.org/en/master/events/index.html

    def PrintDone(self, payload):
        """
        When the print is done, enhance the payload with the filename and the elased time and
        returns it

        :param payload:
        :return:
        """
        self.printing = False
        self.last_minute = 0
        self.last_progress = 0
        self.start_time = None
        file = os.path.basename(payload["name"])
        elapsed_time_in_seconds = payload["time"]

        elapsed_time = octoprint.util.get_formatted_timedelta(
            datetime.timedelta(seconds=elapsed_time_in_seconds)
        )

        # Create the message
        return self._settings.get(["events", "PrintDone", "message"]).format(**locals())

    def PrintFailed(self, payload):
        """
        When the print is failed, enhance the payload with the filename and returns it
        :param payload:
        :return:
        """
        self.printing = False
        if "name" in payload:
            file = os.path.basename(payload["name"])
        return self._settings.get(["events", "PrintFailed", "message"]).format(
            **locals()
        )

    def FilamentChange(self, payload):
        """
        When a M600 command is received the user is asked to change the filament
        :param payload:
        :return:
        """
        m70_cmd = ""
        if self.m70_cmd != "":
            m70_cmd = "(" + self.m70_cmd.strip() + ")"

        return self._settings.get(["events", "FilamentChange", "message"]).format(
            **locals()
        )

    def PrintPaused(self, payload):
        """
        When the print is paused check if there is a m70 command, and replace that in the message.
        :param payload:
        :return:
        """
        m70_cmd = ""
        if self.m70_cmd != "":
            m70_cmd = self.m70_cmd

        return self._settings.get(["events", "PrintPaused", "message"]).format(
            **locals()
        )

    def Waiting(self, payload):
        """
        Alias for PrintPaused
        :param payload:
        :return:
        """
        return self.PrintPaused(payload)

    def PrintStarted(self, payload):
        """
        Reset value's
        :param payload:
        :return:
        """

        self.printing = True
        self.start_time = datetime.datetime.now()
        self.m70_cmd = ""
        self.bed_sent = False
        self.e1_sent = False
        self.first_layer = True
        self.restart_timer()

        if not self.has_own_token():
            return

        return self._settings.get(["events", "PrintStarted", "message"])

    def ZChange(self, payload):
        """
        ZChange event which send a notification, this does not work when printing from sd
        :param payload:
        :return:
        """

        if not self.has_own_token():
            return

        if not self.printing:
            return

        if not self.first_layer:
            return

        # It is not actually the first layer, it was not my plan too create a lot of code for this
        # feature
        if payload["new"] < 2 or payload["old"] is None:
            return

        self.first_layer = False
        return self._settings.get(["events", "ZChange", "message"]).format(**locals())

    def Startup(self, payload):
        """
        Event triggered when printer is started up
        :param payload:
        :return:
        """
        if not self.has_own_token():
            return
        return self._settings.get(["events", "Startup", "message"])

    def Shutdown(self, payload):
        """
        PrinterShutdown
        :param payload:
        :return:
        """
        if not self.has_own_token():
            return
        return self._settings.get(["events", "Shutdown", "message"])

    def Error(self, payload):
        """
        Only continue when the current state is printing
        :param payload:
        :return:
        """
        if self.printing:
            error = payload["error"]
            return self._settings.get(["events", "Error", "message"]).format(**locals())
        return

    #
    # Settings
    #

    def get_settings_version(self):
        return 1

    def on_settings_migrate(self, target, current=None):
        if current is None:
            # If you have the default token, remove it so users will be more triggered to obtain
            # their own.
            if self._settings.get(["token"]) == self._settings.get(["default_token"]):
                self._settings.set(["token"], None)

    def on_settings_save(self, data):
        """
        Valide settings onm save
        :param data:
        :return:
        """
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        try:
            import threading

            thread = threading.Thread(
                target=self.validate_pushover,
                args=(
                    self.get_token(),
                    self._settings.get(["user_key"]),
                ),
            )
            thread.daemon = True
            thread.start()
        except Exception as e:
            self._logger.info(str(e))

        self.restart_timer()

    def on_settings_load(self):
        data = octoprint.plugin.SettingsPlugin.on_settings_load(self)

        # only return our restricted settings to admin users
        # this is only needed for OctoPrint <= 1.2.16
        restricted = ("default_token", "token", "user_key")
        for r in restricted:
            if r in data and (
                current_user is None
                or current_user.is_anonymous()
                or not current_user.is_admin()
            ):
                data[r] = None

        return data

    def get_settings_restricted_paths(self):
        # only used in OctoPrint versions > 1.2.16
        return {"admin": ["default_token", "token", "user_key"]}

    def get_settings_defaults(self):
        return {
            "default_token": "apWqpdodabxA5Uw11rY4g4gC1Vbbrs",
            "token": None,
            "user_key": None,
            "sound": None,
            "device": None,
            "image": None,
            "events": {
                "Scheduled": {
                    "message": "".join(
                        [
                            "Scheduled Notification: {elapsed_time} Minutes Elapsed",
                            self.emoji.get("clock", ""),
                        ]
                    ),
                    "priority": "0",
                    "token_required": True,
                    "custom": True,
                    "mod": 0,
                },
                "Progress": {
                    "message": "Print Progress: {percentage}%",
                    "priority": "0",
                    "token_required": True,
                    "custom": True,
                    "mod": 0,
                },
                "TempReached": {
                    "name": "Temperature Reached",
                    "message": "".join(
                        [
                            self.emoji.get("temp", ""),
                            " | ".join(
                                [
                                    "Temperature Reached! Bed: {bed_temp}/{bed_target}",
                                    "Extruder: {e1_temp}/{e1_target}",
                                ]
                            ),
                        ]
                    ),
                    "priority": "0",
                    "token_required": True,
                },
                "Shutdown": {
                    "name": "Printer Shutdown",
                    "message": "".join(
                        [
                            "Bye bye, I am shutting down ",
                            self.emoji.get("waving_hand_sign", ""),
                        ]
                    ),
                    "priority": "0",
                    "token_required": True,
                },
                "Startup": {
                    "name": "Printer Startup",
                    "message": "".join(
                        [
                            "Hello, Let's print something nice today ",
                            self.emoji.get("waving_hand_sign", ""),
                        ]
                    ),
                    "token_required": True,
                },
                "PrintStarted": {
                    "name": "Print Started",
                    "message": "Print Job Started",
                    "priority": "0",
                    "token_required": True,
                },
                "PrintDone": {
                    "name": "Print Done",
                    "message": "Print Job Finished: {file}, Finished Printing in {elapsed_time}",
                    "priority": "0",
                },
                "PrintFailed": {
                    "name": "Print Failed",
                    "message": "Print Job Failed: {file}",
                    "priority": 0,
                },
                "PrintPaused": {
                    "name": "Print Paused",
                    "help": "Send a notification when a Pause event is received. When a "
                    "<code>m70</code> was sent to the printer, "
                    "the message will be appended to the notification.",
                    "message": "Print Job Paused {m70_cmd}",
                    "priority": 0,
                },
                "Waiting": {
                    "name": "Printer is Waiting",
                    "help": "Send a notification when a Waiting event is received. When a "
                    "<code>m70</code> was sent to the printer, "
                    "the message will be appended to the notification.",
                    "message": "Printer is Waiting {m70_cmd}",
                    "priority": 0,
                },
                "FilamentChange": {
                    "name": "Filament Change",
                    "help": "Send a notification when a M600 (Filament Change) command is received. "
                    "When a <code>m70</code> was sent to the printer, "
                    "the message will be appended to the notification.",
                    "message": "Please change the filament {m70_cmd}",
                    "priority": 0,
                },
                "ZChange": {
                    "name": "After first couple of layer",
                    "help": "Send a notification when the 'first' couple of layers is done.",
                    "message": "".join(
                        [
                            "First couple of layers are done ",
                            self.emoji.get("four_leaf_clover", ""),
                        ]
                    ),
                    "priority": 0,
                    "token_required": True,
                },
                "Alert": {
                    "name": "Alert Event (M300)",
                    "message": "Alert! The printer issued a alert (beep) via M300",
                    "priority": 1,
                    "hidden": True,
                },
                "EStop": {
                    "name": "Panic Event (M112)",
                    "message": "Panic!! The printer issued a panic stop (M112)",
                    "priority": 1,
                    "hidden": True,
                },
                # See: src/octoprint/util/comm.py:2009
                "Error": {
                    "name": "Error Event",
                    "help": "This event occurs when for example your temperature sensor disconnects.",
                    "message": "Error!! An error has occurred in the printer communication. {error}",
                    "priority": 1,
                    "hidden": True,
                },
            },
        }

    #
    # Pushover
    #

    def event_message(self, payload):
        """
        Do send the notification to the cloud :)
        :param payload:
        :return:
        """
        # Create an url, if the fqdn is not correct you can manually set it at your config.yaml
        url = self._settings.get(["url"])
        if url:
            payload["url"] = url
        else:
            # Create an url
            import socket

            payload["url"] = "http://%s" % socket.getfqdn()

        if "token" not in payload:
            payload["token"] = self.get_token()

        if "user" not in payload:
            payload["user"] = self._settings.get(["user_key"])

        if "sound" not in payload:
            # If no sound parameter is specified, the user"s default tone will play.
            # If the user has not chosen a custom sound, the standard Pushover sound will play.
            sound = self._settings.get(["sound"])
            if sound:
                payload["sound"] = sound

        if "device" not in payload:
            # If no device parameter is specified, get it from the settings.
            device = self._settings.get(["device"])
            if device:
                payload["device"] = device

        if (
            self._printer_profile_manager is not None
            and "name" in self._printer_profile_manager.get_current_or_default()
        ):
            payload["title"] = (
                "Octoprint: %s"
                % self._printer_profile_manager.get_current_or_default()["name"]
            )

        files = {}
        try:
            if self._settings.get(["image"]) or (
                "image" in payload and payload["image"]
            ):
                files["attachment"] = ("image.jpg", self.image())
        except Exception as e:
            self._logger.info("Could not load image from url")

        # Multiple try catches so it will always send a message if the image raises an Exception
        try:
            r = requests.post(
                self.api_url + "/messages.json", files=files, data=payload
            )
            self._logger.debug("Response: %s" % str(r.content))
        except Exception as e:
            self._logger.info("Could not send message: %s" % str(e))

    def has_own_token(self):
        return self.get_token() != self._settings.get(["default_token"])

    def get_token(self):
        if not self._settings.get(["token"]):
            # If an users don't want an own API key, it is ok, you can use mine.
            return self._settings.get(["default_token"])
        return self._settings.get(["token"])

    def validate_pushover(self, api_key, user_key):
        """
        Validate settings, this will do a post request to users/validate.json
        :param user_key:
        :return:
        """
        if not api_key:
            raise ValueError("No api key provided")
        if not user_key:
            raise ValueError("No user key provided")

        try:
            r = requests.post(
                self.api_url + "/users/validate.json",
                data={
                    "token": api_key,
                    "user": user_key,
                },
            )

            if r is not None and not r.status_code == 200:
                raise ValueError(
                    f"error while instantiating Pushover, header {r.status_code}"
                )

            response = json.loads(r.content)

            if response["status"] == 1:
                self._logger.info("Connected to Pushover")

                return True

        except Exception as e:
            raise ValueError(f"error while instantiating Pushover: {e}") from e

        return False

    def get_sounds(self):
        try:
            r = requests.get(self.api_url + "/sounds.json?token=" + self.get_token())
            return json.loads(r.content)["sounds"]
        except Exception as e:
            self._logger.debug(str(e))
            return {}

    #
    # UI
    #

    def get_template_configs(self):
        return [{"type": "settings", "name": "Pushover", "custom_bindings": True}]

    def get_template_vars(self):
        return {
            "sounds": self.get_sounds(),
            "events": self.get_settings_defaults()["events"],
        }

    #
    # Unknown Functionality
    #

    # TODO: refactor
    def image(self):
        """
        Create an image by getting an image form the setting webcam-snapshot.
        Transpose this image according the settings and returns it
        :return:
        """
        snapshot_url = self._settings.global_get(["webcam", "snapshot"])
        if not snapshot_url:
            return None

        self._logger.debug(f"Snapshot URL: {snapshot_url}")
        try:
            image = requests.get(snapshot_url, stream=True).content
        except HTTPError as http_err:
            self._logger.info(
                f"HTTP error occured while trying to get image: {http_err}"
            )
        except Exception as err:
            self._logger.info(f"Other error occurred while trying to get image: {err}")

        hflip = self._settings.global_get(["webcam", "flipH"])
        vflip = self._settings.global_get(["webcam", "flipV"])
        rotate = self._settings.global_get(["webcam", "rotate90"])
        if hflip or vflip or rotate:
            # https://www.blog.pythonlibrary.org/2017/10/05/how-to-rotate-mirror-photos-with-python/
            image_obj = Image.open(BytesIO(image))
            if hflip:
                image_obj = image_obj.transpose(Image.FLIP_LEFT_RIGHT)
            if vflip:
                image_obj = image_obj.transpose(Image.FLIP_TOP_BOTTOM)
            if rotate:
                image_obj = image_obj.rotate(90)
            # https://stackoverflow.com/questions/646286/python-pil-how-to-write-png-image-to-string/5504072
            output = BytesIO()
            image_obj.save(output, format="JPEG")
            image = output.getvalue()
            output.close()

        return image

    # TODO: refactor
    def restart_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

        if self.has_own_token() and self._settings.get(
            ["events", "TempReached", "priority"]
        ):
            self.timer = RepeatedTimer(5, self.temp_check, None, None, True)
            self.timer.start()

    def temp_check(self):

        if not self.has_own_token():
            return

        if not self._printer.is_operational():
            return

        if self._settings.get(["events", "TempReached", "priority"]):

            temps = self._printer.get_current_temperatures()

            bed_temp = round(temps["bed"]["actual"]) if "bed" in temps else 0
            bed_target = temps["bed"]["target"] if "bed" in temps else 0
            e1_temp = round(temps["tool0"]["actual"]) if "tool0" in temps else 0
            e1_target = temps["tool0"]["target"] if "tool0" in temps else 0

            if bed_target > 0 and bed_temp >= bed_target and self.bed_sent is False:
                self.bed_sent = True

                self.event_message(
                    {
                        "message": self._settings.get(
                            ["events", "TempReached", "message"]
                        ).format(**locals())
                    }
                )

            if e1_target > 0 and e1_temp >= e1_target and self.e1_sent is False:
                self.e1_sent = True

                self.event_message(
                    {
                        "message": self._settings.get(
                            ["events", "TempReached", "message"]
                        ).format(**locals())
                    }
                )

    def get_mins_since_started(self):
        if self.start_time:
            return int(
                round(
                    (datetime.datetime.now() - self.start_time).total_seconds() / 60, 0
                )
            )



__plugin_name__ = "Pushover"


def __plugin_load__():
    # pylint: disable=line-too-long, global-variable-undefined

    global __plugin_implementation__
    __plugin_implementation__ = PushoverPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.sent_gcode,
    }
