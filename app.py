from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, timedelta
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


def restore_after_delay(
    light_client: HikvisionLightClient,
    endpoint: str,
    backup_xml: bytes,
) -> None:
    try:
        light_client.put_configuration(endpoint, backup_xml)
    except Exception:
        # The manual restore button and downloaded XML remain the safe fallback.
        pass


def show_configuration(values: dict[str, str]) -> None:
    useful = {
        key: value
        for key, value in values.items()
        if key
        in {
            "mode",
            "enabled",
            "supplementLightMode",
            "mixedLightBrightnessRegulatMode",
            "brightnessRegulateMode",
            "brightnessLimit",
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
        st.session_state.light_current_xml = current.xml
        st.success("Current supplementary-light settings loaded.")
    except LightControlError as exc:
        st.error(str(exc))

if st.session_state.get("light_endpoint"):
    st.caption(f"Detected endpoint: {escape(st.session_state.light_endpoint)}")
    show_configuration(st.session_state.get("light_values", {}))
    if st.session_state.get("light_current_xml"):
        st.download_button(
            "Download current raw light configuration",
            data=st.session_state.light_current_xml,
            file_name="zalongwa-current-light-settings.xml",
            mime="application/xml",
            use_container_width=True,
        )

st.divider()
st.subheader("Temporary light shutoff")

off_minutes = st.selectbox(
    "Automatically turn the light back on after",
    options=[1, 5, 10, 15, 30, 60],
    index=2,
    format_func=lambda minutes: f"{minutes} minute" if minutes == 1 else f"{minutes} minutes",
)

if st.button(
    "Turn light off temporarily",
    type="primary",
    use_container_width=True,
):
    try:
        with st.spinner("Saving current settings and switching the light off…"):
            backup = light_client.turn_off()
            current = light_client.get_configuration()

        old_timer = st.session_state.get("light_restore_timer")
        if old_timer is not None:
            old_timer.cancel()

        timer = threading.Timer(
            off_minutes * 60,
            restore_after_delay,
            args=(light_client, backup.endpoint, backup.xml),
        )
        timer.daemon = True
        timer.start()

        st.session_state.light_restore_timer = timer
        st.session_state.light_backup_xml = backup.xml
        st.session_state.light_endpoint = current.endpoint
        st.session_state.light_values = current.values
        st.session_state.light_restore_at = datetime.now() + timedelta(minutes=off_minutes)
        st.success(
            f"Supplementary light switched off. It is scheduled to return automatically "
            f"at {st.session_state.light_restore_at.strftime('%H:%M:%S')}."
        )
    except LightControlError as exc:
        st.error(str(exc))

backup_xml = st.session_state.get("light_backup_xml")
if backup_xml:
    restore_at = st.session_state.get("light_restore_at")
    if restore_at:
        st.info(f"Automatic restoration scheduled for {restore_at.strftime('%H:%M:%S')}.")
    st.download_button(
        "Download previous light settings",
        data=backup_xml,
        file_name="zalongwa-light-backup.xml",
        mime="application/xml",
        use_container_width=True,
    )

    if st.button("Turn light back on now", use_container_width=True):
        try:
            with st.spinner("Restoring the previous light settings…"):
                restored = light_client.restore(backup_xml)
            timer = st.session_state.pop("light_restore_timer", None)
            if timer is not None:
                timer.cancel()
            st.session_state.pop("light_restore_at", None)
            st.session_state.light_endpoint = restored.endpoint
            st.session_state.light_values = restored.values
            st.success("The supplementary light was restored immediately.")
        except LightControlError as exc:
            st.error(str(exc))

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
        timer = st.session_state.pop("light_restore_timer", None)
        if timer is not None:
            timer.cancel()
        st.session_state.pop("light_restore_at", None)
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
