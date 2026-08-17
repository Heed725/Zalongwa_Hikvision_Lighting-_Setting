# Zalongwa Hikvision Supplementary Light Control

A protected Streamlit administrator app for remotely checking, switching off, and restoring the supplementary light configuration of a compatible Hikvision face-recognition terminal.

## Features

- Detects the supported Hikvision ISAPI supplementary-light endpoint.
- Displays the current light configuration.
- Saves the terminal's exact current XML configuration before changing anything.
- Turns off supported light/brightness fields for a selected duration.
- Automatically restores the exact previous settings after 1, 5, 10, 15, 30, or 60 minutes.
- Provides a **Turn light back on now** button.
- Downloads a backup XML for safe storage.
- Restores the exact previous configuration from the current session or an uploaded backup.
- Requires a separate administrator PIN.
- Keeps the device URL, username, password, and PIN in Streamlit Secrets.

## Streamlit Cloud deployment

1. Deploy this repository in Streamlit Community Cloud.
2. Set the main file to `app.py`.
3. Open **Advanced settings → Secrets**.
4. Add:

```toml
HIKVISION_URL = "http://PUBLIC_IP:PORT"
HIKVISION_USERNAME = "admin"
HIKVISION_PASSWORD = "YOUR_DEVICE_PASSWORD"
HIKVISION_TIMEOUT = "45"
HIKVISION_VERIFY_TLS = "false"
LIGHT_ADMIN_PIN = "YOUR_SEPARATE_PRIVATE_PIN"
```

5. Save the secrets and reboot the app.

Never commit real credentials. The device must be reachable from Streamlit Cloud.

## Safe workflow

1. Sign in with the separate light-control PIN.
2. Click **Read current light settings**.
3. Choose how long the light should remain off and click **Turn light off temporarily**.
4. Download and keep the generated `zalongwa-light-backup.xml`.
5. The app automatically restores the previous settings when the timer ends. To restore sooner, click **Turn light back on now**. You can also upload the saved XML after a restart.

The app restores the exact saved configuration instead of guessing brightness or automatic-mode defaults.

## Local run

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
streamlit run app.py
```

Turning the light off can reduce face-recognition performance in dark conditions.

## Automatic-restore note

Automatic restoration uses a background timer in the running Streamlit server. Keep the deployment awake during the selected period. The immediate restore button and downloaded backup XML remain available as fallbacks if the hosting service restarts or sleeps.

## DS-K1T321 supplementary-light schema

The Zalongwa face terminal uses the access-terminal fields `mode` and `brightnessLimit`. Temporary shutoff sets `mode` to `off` and `brightnessLimit` to `0`, then restores the exact original XML when the timer ends. The app also provides a raw configuration download for diagnostics.
