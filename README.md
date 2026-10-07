# Meraki Config Manager V2

A browser-based management tool for Cisco Meraki MX networks. Run it locally or in Docker — no cloud account required.

---

## Features

| Feature | Description |
|---|---|
| **Dashboard** | Network count, total VPN exclusion rules, org overview |
| **Networks** | Browse and search all MX networks in your organization |
| **VPN Exclusions** | View, import (CSV/XLSX/JSON), dry-run, and deploy split-tunnel rules |
| **Copy Rules** | Copy VPN exclusion rules across multiple networks with a 5-step wizard |
| **Group Policies** | Server-side dry run, safe skip or full overwrite, drift protection, and session-only rollback |
| **Compare Networks** | Side-by-side diff of VPN rules, SSIDs, and appliance settings |
| **New Network Wizard** | Create a new network cloned from a template in 6 guided steps |
| **Activity Log** | Timestamped log of every action taken during your session |

---

## Requirements

- Python **3.10+**
- A [Cisco Meraki Dashboard API key](https://developer.cisco.com/meraki/api-v1/authorization/)

---

## Quick Start

### macOS / Linux

```bash
git clone https://github.com/shayiqbal/meraki-client-web-localv2.git
cd meraki-client-web-localv2
bash run_web.sh
```

The script will:
1. Create a Python virtual environment (`.web_venv/`)
2. Install all dependencies
3. Start a local-only server and open `http://127.0.0.1:8000` in your browser automatically

---

### Windows

```bat
git clone https://github.com/shayiqbal/meraki-client-web-localv2.git
cd meraki-client-web-localv2
run_web.bat
```

Double-click `run_web.bat` or run it from Command Prompt. Same steps as above.

---

### Docker

```bash
git clone https://github.com/shayiqbal/meraki-client-web-localv2.git
cd meraki-client-web-localv2
docker build -t meraki-config-manager-v2 .
docker run -p 127.0.0.1:8000:8000 meraki-config-manager-v2
```

Then open `http://127.0.0.1:8000` in your browser.

---

## Usage

1. Open `http://127.0.0.1:8000`
2. Paste your **Meraki Dashboard API key** and click **Connect**
3. Select your **organization** from the dropdown in the top bar
4. Use the sidebar to navigate between features

---

## Group Policy Safety

- Run a dry run before every Group Policy operation. It reads Meraki configuration but makes no changes.
- Existing same-named policies can be skipped (default) or overwritten in place. Overwrite applies every writable setting returned by Meraki for the source policy, including rules, while retaining the destination policy ID and assignments.
- Execution verifies destination policies have not changed since the dry run. Re-run the dry run if it reports drift.
- V2 keeps rollback data only in the active session. Roll back before logout, expiry, or restart. Rollback stops if a policy changed after V2 updated it.

## Security

- The default launch binds only to `127.0.0.1`; it is not reachable from the LAN.
- Your API key is validated live against Meraki, held only in server memory for the active session, and is not stored in browser storage, rollback data, or normal logs.
- Browser authentication uses an `HttpOnly`, `SameSite=Strict` cookie plus CSRF protection; the session token is not readable by JavaScript.
- Sessions expire after **2 hours** of inactivity or **8 hours** total.
- Do not expose V2 directly to a network. Remote deployment requires HTTPS through a trusted reverse proxy and separate deployment hardening.
