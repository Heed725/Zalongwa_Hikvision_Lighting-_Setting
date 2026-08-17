from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests
from requests.auth import HTTPDigestAuth
from requests.exceptions import RequestException


class LightControlError(RuntimeError):
    pass


@dataclass
class LightConfiguration:
    endpoint: str
    xml: bytes
    values: dict[str, str]


ENDPOINTS = (
    "/ISAPI/Image/channels/1/supplementLight",
    "/ISAPI/Image/channels/1/SupplementLight",
    "/ISAPI/System/externalDevice/supplementLight",
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _values(xml: bytes) -> dict[str, str]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise LightControlError("The terminal returned invalid supplementary-light XML.") from exc
    return {
        _local_name(node.tag): (node.text or "").strip()
        for node in root.iter()
        if len(node) == 0
    }


def _response_error(response: requests.Response) -> str:
    try:
        values = _values(response.content)
        return values.get("subStatusCode") or values.get("statusString") or response.reason
    except LightControlError:
        return response.reason or f"HTTP {response.status_code}"


class HikvisionLightClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: int = 45,
        verify_tls: bool = False,
    ):
        if not base_url.startswith(("http://", "https://")):
            raise LightControlError("HIKVISION_URL must start with http:// or https://")
        if not username or not password:
            raise LightControlError("Hikvision username and password are not configured.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(username, password)
        self.session.headers.update(
            {
                "User-Agent": "Zalongwa-Hikvision-Light-Control/1.0",
                "Connection": "close",
            }
        )

    def request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify_tls)
        try:
            response = self.session.request(
                method, f"{self.base_url}{endpoint}", **kwargs
            )
        except RequestException as exc:
            raise LightControlError(f"Could not reach the Hikvision terminal: {exc}") from exc
        if response.status_code == 401:
            raise LightControlError("Hikvision authentication failed.")
        return response

    def get_configuration(self) -> LightConfiguration:
        unsupported = []
        for endpoint in ENDPOINTS:
            response = self.request("GET", endpoint)
            if response.ok and response.content.strip():
                try:
                    values = _values(response.content)
                except LightControlError:
                    unsupported.append(f"{endpoint}: unreadable response")
                    continue
                return LightConfiguration(endpoint, response.content, values)
            unsupported.append(f"{endpoint}: {_response_error(response)}")
        raise LightControlError(
            "This firmware did not accept the known supplementary-light endpoints. "
            + " | ".join(unsupported)
        )

    @staticmethod
    def make_off_configuration(xml: bytes) -> bytes:
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise LightControlError("Cannot modify an invalid light configuration.") from exc

        if root.tag.startswith("{"):
            ET.register_namespace("", root.tag[1:].split("}", 1)[0])

        changed = []
        for node in root.iter():
            name = _local_name(node.tag)
            if name == "mode":
                # Face-recognition terminals use: schedule, off, on, auto, manual.
                node.text = "off"
                changed.append(name)
            elif name == "enabled":
                node.text = "false"
                changed.append(name)
            elif name in {
                "brightnessLimit",
                "whiteLightBrightness",
                "brightness",
                "maxBrightness",
                "whiteLightBrightnessLimit",
            }:
                node.text = "0"
                changed.append(name)

        if not changed:
            raise LightControlError(
                "The terminal configuration has no recognised on/off or brightness field. "
                "No change was sent."
            )
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def put_configuration(self, endpoint: str, xml: bytes) -> None:
        # Validate before sending and restrict uploaded backups to SupplementLight XML.
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise LightControlError("The backup is not valid XML.") from exc
        if _local_name(root.tag).lower() != "supplementlight":
            raise LightControlError("The uploaded XML is not a SupplementLight configuration.")

        response = self.request(
            "PUT",
            endpoint,
            data=xml,
            headers={"Content-Type": "application/xml"},
        )
        if not response.ok:
            raise LightControlError(
                f"The terminal rejected the light setting: {_response_error(response)}"
            )

    def turn_off(self) -> LightConfiguration:
        current = self.get_configuration()
        disabled_xml = self.make_off_configuration(current.xml)
        self.put_configuration(current.endpoint, disabled_xml)
        return current

    def restore(self, xml: bytes) -> LightConfiguration:
        current = self.get_configuration()
        self.put_configuration(current.endpoint, xml)
        return self.get_configuration()
