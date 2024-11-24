"""
Interact with the Pushover service.
"""

from datetime import datetime
from dataclasses import dataclass
from typing import Any, Optional
from enum import IntEnum

from requests import RequestException, post, Response
from requests.exceptions import JSONDecodeError


@dataclass
class Attachment:
    """
    An attachment that can be embedded into a message.
    """

    data: bytes
    mimetype: str


class Priority(IntEnum):
    VERY_LOW = -2
    LOW = -1
    DEFAULT = 0
    HIGH = 1
    VERY_HIGH = 1


class PushoverError(Exception):
    """
    Represents errors generated from Pushover requests.
    """

    def __init__(
        self,
        message: str,
        *args,
        response: Optional[Response] = None,
    ):
        super().__init__(*args)

        self.message = message
        self.response = response


class Pushover:
    """
    Interact with the Pushover service.
    """

    BASE_URL = "https://api.pushover.net/1"

    def __init__(self, token: str, user: str, timeout: Optional[float] = 10):
        self.token = token
        self.user = user
        self.timeout = timeout

    def _request_body(self, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        data = dict(data) if data is not None else {}
        data["token"] = self.token
        data["user"] = self.user

        return data

    def validate(self) -> bool:
        """
        Validates the user's token.

        Will return a boolean when the status is successfully returned from Pushover,
        otherwise will raise an exception.

        :returns: whether the user can send messages via Pushover
        """

        try:
            response = post(
                f"{self.BASE_URL}/validate.json",
                data=self._request_body(),
                timeout=self.timeout,
            )
        except RequestException as e:
            raise PushoverError("Failed to send request to Pushover") from e

        if response.status_code != 200:
            raise PushoverError(
                f"Pushover returned {response.status_code}",
                response=response,
            )

        try:
            return response.json()["status"] == "1"
        except (JSONDecodeError, KeyError) as e:
            raise PushoverError(
                "Failed to parse response",
                response=response,
            ) from e

    def send_message(
        self,
        message: str,
        title: Optional[str] = None,
        url: Optional[str] = None,
        url_title: Optional[str] = None,
        attachment: Optional[Attachment] = None,
        device: Optional[str] = None,
        html: bool = False,
        priority: Priority = Priority.DEFAULT,
        sound: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        ttl: Optional[int] = None,
    ):
        # pylint: disable=too-many-arguments
        """
        Send a message.

        :param message: your message
        :param title: your message's title, otherwise your app's name is used
        :param url: a supplementary URL to show with your message
        :param url_title: an optional title for the URL specified as the url parameter
        :param attachment: a binary image attachment to send with the message
        :param device: the name of one of your devices to send just to that device instead of all
        :param html: whether to allow some limited markup (see https://pushover.net/api#html)
        :param priority:
        :param sound: the name of a supported sound to override your default sound choice
        :param timestamp: a timestamp of a time to display instead of when our API received it
        :param ttl: a number of seconds that the message will live, before being auto-deleted
        """

        files: Optional[dict[str, bytes]] = None
        data: dict[str, Any] = self._request_body({"message": message})

        if title is not None:
            data["title"] = title

        if url is not None:
            data["url"] = url
            if url_title is not None:
                data["url_title"] = url_title

        if attachment is not None:
            files = {"attachment": attachment.data}
            data["attachment_type"] = attachment.mimetype

        if device is not None:
            data["device"] = device

        if html:
            data["html"] = "1"

        if priority != Priority.DEFAULT:
            data["priority"] = int(priority)

        if sound is not None:
            data["sound"] = sound

        if timestamp is not None:
            data["timestamp"] = int(timestamp.timestamp())

        if ttl is not None:
            data["ttl"] = ttl

        post(
            f"{self.BASE_URL}/messages.json",
            data=data,
            files=files,
            timeout=self.timeout,
        )
