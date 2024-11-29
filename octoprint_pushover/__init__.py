"""
Module entry point for Pushover notifications.
"""

from .plugin import PushoverPlugin

__author__ = "Thijs Bekke <thijsbekke@gmail.com>, Raresh Nistor <raresh@nistor.email>"
__license__ = "GNU Affero General Public License http://www.gnu.org/licenses/agpl.html"
__copyright__ = "Released under terms of the AGPLv3 License"
__plugin_name__ = "Pushover"
__plugin_pythoncompat__ = ">=3.7,<4"

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
