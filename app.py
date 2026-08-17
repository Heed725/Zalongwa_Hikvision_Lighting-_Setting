from __future__ import annotations

import hashlib
import os
from html import escape

import streamlit as st

from lighting import HikvisionLightClient, LightControlError


st.set_page_config(
    page_title="Zalongwa Hikvision Light Control",
    page_icon="💡",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def setting(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)


def safe_equal(left: str, right: str) -> bool:
    return bool(left and right) and (
        hashlib.sha256(left.encode()).digest()
        == hashlib.sha256(right.encode()).digest()
    )


def client() -> HikvisionLightClient:
    return HikvisionLightClient(
        setting("HIKVISION_URL"),
        setting("HIKVISION_USERNAME", "admin"),
        setting("HIKVISION_PASSWORD"),
        int(setting("HIKVISION_TIMEOUT", "45")),
        setting("HIKVISION_VERIFY_TLS", "false").lower() == "true",
    )


def show_configuration(values: dict[str, str]) -> None:
    useful = {
        key: value
        for key, value in values.items()
        if key
        in {
            "enabled",
            "supplementLightMode",
            "mixedLightBrightnessRegulatMode",
            "brightnessRegulateMode",
            "whiteLightBrightness",
            "brightness",
            "maxBrightness",
            "whiteLightBrightnessLimit",
        }
    }
    if useful:
        st.table([{"Setting": key, "Value": value} for key, value in useful.items()])
    else:
        st.info("The terminal returned a light configuration without standard display fields.")


st.title("Zalongwa Hikvision Light Control")
st.caption("Administrator-only supplementary light control")

required = (
    setting("HIKVISION_URL"),
    setting("HIKVISION_PASSWORD"),
    setting("LIGHT_ADMIN_PIN"),
)
if not all(required):
    st.error(
        "Configure the Hikvision URL, device password and LIGHT_ADMIN_PIN "
        "in Streamlit Secrets."
    )
    st.stop()

if not st.session_state.get("light_admin_authorized"):
    with st.form("light_admin_login"):
        pin = st.text_input("Light-control administrator PIN", type="password")
        submitted = st.form_submit_button(
            "Open light controls", type="primary", use_container_width=True
        )
    if submitted:
        if safe_equal(pin, setting("LIGHT_ADMIN_PIN")):
            st.session_state.light_admin_authorized = True
            st.rerun()
        else:
            st.error("Incorrect light-control administrator PIN.")
    st.stop()

if st.button("Sign out", use_container_width=True):
    for key in (
        "light_admin_authorized",
        "light_backup_xml",
        "light_endpoint",
        "light_values",
    ):
        st.session_state.pop(key, None)
    st.rerun()

st.warning(
    "Turning off the supplementary light can reduce face recognition accuracy "
    "in dark conditions."
)

try:
    light_client = client()
except LightControlError as exc:
    st.error(str(exc))
    st.stop()

if st.button("Read current light settings", use_container_width=True):
    try:
        with st.spinner("Reading the terminal light configuration…"):
            current = light_client.get_configuration()
        st.session_state.light_endpoint = current.endpoint
        st.session_state.light_values = current.values
        st.success("Current supplementary-light settings loaded.")
    except LightControlError as exc:
        st.error(str(exc))

if st.session_state.get("light_endpoint"):
    st.caption(f"Detected endpoint: {escape(st.session_state.light_endpoint)}")
    show_configuration(st.session_state.get("light_values", {}))

st.divider()
st.subheader("Turn light off")

if st.button(
    "Turn supplementary light off",
    type="primary",
    use_container_width=True,
):
    try:
        with st.spinner("Saving current settings and switching the light off…"):
            backup = light_client.turn_off()
            current = light_client.get_configuration()
        st.session_state.light_backup_xml = backup.xml
        st.session_state.light_endpoint = current.endpoint
        st.session_state.light_values = current.values
        st.success(
            "Supplementary light switched off. Download the backup before leaving."
        )
    except LightControlError as exc:
        st.error(str(exc))

backup_xml = st.session_state.get("light_backup_xml")
if backup_xml:
    st.download_button(
        "Download previous light settings",
        data=backup_xml,
        file_name="zalongwa-light-backup.xml",
        mime="application/xml",
        use_container_width=True,
    )

st.divider()
st.subheader("Restore normal/previous settings")
uploaded_backup = st.file_uploader(
    "Upload zalongwa-light-backup.xml if this session was restarted",
    type=["xml"],
)
restore_xml = uploaded_backup.getvalue() if uploaded_backup else backup_xml

if st.button(
    "Restore previous settings",
    use_container_width=True,
    disabled=restore_xml is None,
):
    try:
        with st.spinner("Restoring the saved supplementary-light configuration…"):
            restored = light_client.restore(restore_xml)
        st.session_state.light_endpoint = restored.endpoint
        st.session_state.light_values = restored.values
        st.success("The exact previous supplementary-light settings were restored.")
    except LightControlError as exc:
        st.error(str(exc))

if restore_xml is None:
    st.info(
        "Turn the light off in this session or upload the downloaded backup XML "
        "to enable restoration."
    )
