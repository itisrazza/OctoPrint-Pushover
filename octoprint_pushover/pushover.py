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
    """
    Message priorities.
    """

    LOWEST = -2
    LOW = -1
    NORMAL = 0
    HIGH = 1
    EMERGENCY = 2


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

    @classmethod
    def request_fail(cls):
        """Creates a new PushoverException for when a request fails to send to Pushover."""
        return cls("Failed to send request to Pushover")

    @classmethod
    def status_code(cls, response: Response):
        """
        Creates a new PushoverException for when Pushover responds with
        an unexpected status code.
        """
        return cls(
                f"Pushover returned {response.status_code}",
                response=response,
            )

    @classmethod
    def parse_fail(cls, response: Response):
        """Creates a new PushoverException for when a response cannot be parsed."""
        return PushoverError(
                "Failed to parse response",
                response=response,
            )

    @classmethod
    def request_reject(cls, response: Response):
        """Creates a new PushoverException for when Pushover rejects a request (status code 4xx)."""
        return PushoverError("Pushover rejected the message request", response=response)


@dataclass
class MessageResponse:
    """
    Values provided by Pushover for message responses.

    :param receipt: if the message priority was set to EMERGENCY (2), this will return an ID to be
                    used with the receipts API.
    :param request: the request ID
    """

    receipt: Optional[str]
    request: str


class Pushover:
    """
    Interact with the Pushover service.
    """

    BASE_URL = "https://api.pushover.net/1"

    def __init__(self, token: str, user: str, timeout: Optional[float] = 10):
        self.token = token
        self.user = user
        self.timeout = timeout

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
            raise PushoverError.request_fail() from e

        if response.status_code != 200:
            raise PushoverError.status_code(response)

        try:
            return response.json()["status"] == "1"
        except (JSONDecodeError, KeyError) as e:
            raise PushoverError.parse_fail(response) from e

    def send_message(
        self,
        message: str,
        title: Optional[str] = None,
        url: Optional[str] = None,
        url_title: Optional[str] = None,
        attachment: Optional[Attachment] = None,
        device: Optional[str] = None,
        html: bool = False,
        priority: Priority = Priority.NORMAL,
        sound: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        ttl: Optional[int] = None,
    ):
        """
        Send a message through Pushover.

        :param message: your message
        :param title: your message's title, otherwise your app's name is used
        :param url: a supplementary URL to show with your message
        :param url_title: an optional title for the URL specified as the url parameter
        :param attachment: a binary image attachment to send with the message
        :param device: the name of one of your devices to send just to that device instead of all
        :param html: whether to allow some limited markup (see https://pushover.net/api#html)
        :param priority: message priority
        :param sound: the name of a supported sound to override your default sound choice
        :param timestamp: a timestamp of a time to display instead of when our API received it
        :param ttl: a number of seconds that the message will live, before being auto-deleted
        """
        # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches

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

        if priority != Priority.NORMAL:
            data["priority"] = int(priority)

        if sound is not None:
            data["sound"] = sound

        if timestamp is not None:
            data["timestamp"] = int(timestamp.timestamp())

        if ttl is not None:
            data["ttl"] = ttl

        try:
            response = post(
                f"{self.BASE_URL}/messages.json",
                data=data,
                files=files,
                timeout=self.timeout,
            )
        except RequestException as e:
            raise PushoverError.request_fail() from e

        if response.status_code in range(400, 500):
            raise PushoverError.request_reject(response)

        if response.status_code != 200:
            raise PushoverError.status_code(response)

        try:
            payload = response.json()
            return MessageResponse(payload.get("receipt", None), payload["request"])
        except (JSONDecodeError, KeyError) as e:
            raise PushoverError.parse_fail(response) from e


    def _request_body(self, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        data = dict(data) if data is not None else {}
        data["token"] = self.token
        data["user"] = self.user

        return data
