# Your Assistant Agent 4.9

A personal Windows assistant with its own Android 1.5 companion, shared branding,
remote desktop, file transfers and reviewed GitHub/Facebook tools.

Android **1.5.1** fixes an immediate crash on the Scan QR button: ZXing's
published dependency metadata omitted AndroidX classes needed at runtime.
See [the QR scanner fix and update steps](README_ANDROID_V151_AR.md).

## Facebook, Arabic and dictation fixes

Facebook chat commands now open an interactive controlled browser and keep its
profile alive for login, group discovery and page/post reads. Playwright runs on
one owner thread across desktop and mobile requests. The extension remains an
optional route. New read-only tools find pages and visible post links; posting
still requires a preview and approval. Explicit examples do not execute tasks.

Windows chat uses the built-in Unicode RichEdit editor for Arabic shaping,
paragraph direction and caret behavior, preserving logical text and clipboard
order. Finishing dictation retains the captured tail and never auto-sends it.
Recognition still depends on the recording and the speech provider.

[Start with the Arabic 4.9 update guide](README_V490_AR.md). Native Windows
rendering and the owner's Facebook session still require device validation;
Linux checks do not establish those results.

## Host the connection on your own computer

Open **Pair phone QR → Start hosting and show QR** in the unlocked Windows app.
The app starts its own HTTPS listener, generates a persistent certificate, and
displays a QR. Scan it from Android on the same home network. No external relay
account, VPN app, domain or paid hosting is required for this mode.

The certificate private key is encrypted with the app's local security key.
Android trusts the exact certificate fingerprint from QR, scoped to each
connection. Standard CA verification remains unchanged for legacy HTTPS mode.
The pairing token is stored using Android Keystore. Keep QR private; rotate the
pairing token from Windows to revoke previously paired phones.

[Network and router requirements](README_V480_AR.md).

## Access away from home

The QR may contain a LAN address and an optional public HTTPS address. Reads can
try another address when the selected one is unreachable. A mutating request is
not automatically replayed at another address after an uncertain failure.

Internet reachability requires either:

- Public IPv4 with a router TCP port forward to the Windows listener, normally
  port 8443, and a Windows Firewall rule allowing the application.
- Reachable global IPv6 with suitable router and Windows firewall permissions.

CGNAT without reachable IPv6 cannot be solved by QR or a single home computer
without an outside intermediary. The provider may restrict incoming traffic.
Address changes require an updated QR unless the owner chooses a stable DNS
name. A successful LAN test does not prove access from a mobile data network.
No router mappings or firewall rules are changed automatically.

## Desktop, files and AI

The owner chooses screen/input/file permissions and can expose all local fixed
and removable drives, or a selected folder. Android supports primary-monitor
frames, clicks, right/double clicks, dragging, zoom, Unicode typing and keyboard
shortcuts. Individual files up to 256 MiB can be transferred with progress.
Uploads refuse to overwrite existing files. ZIP-to-GitHub uses a separate 20 MiB
limit and review/approval before commit or push.

Keep the PC awake, the assistant unlocked and the Windows session open. The
optional AC power guard prevents idle sleep while the companion runs. It does
not wake the computer or override manual sleep, lid behavior, lock screens,
UAC/secure desktop, elevated-process restrictions or website authentication.
There is no audio streaming, high-frame-rate video or multi-monitor selection.

Screen and manual file/control data use a direct encrypted connection in home
hosting mode. **Conversation and computer-AI tasks still use GroqCloud**
(`openai/gpt-oss-120b`); relevant chat and visible UI labels can be sent there.
This release does not add an offline AI model. Computer AI uses observed
accessibility elements, takes task approval and re-observes after actions;
applications exposing sparse accessibility data need manual desktop control.

The Android app reconnects while open; it does not add background notifications.
See [the 4.7 guide](README_V470_AR.md) for desktop controls and release signing.
The optional older external relay remains available in advanced settings; see
[the 4.6 guide](README_V460_AR.md) only if using that separate mode.

## Build and install

Source ZIPs are not Windows installers. Upload the source to your repository
root and run `.github/workflows/build-windows.yml`. It builds Windows installer
artifact **YourAssistantAgent-Windows-Setup-v4.9.0** and Android Debug. Private
Android signing secrets additionally enable **YourAssistantAgent-Android-Release-v1.5.1**.
Never commit signing files or `desktop-setup.json`.

For source use, install Python 3.11 and dependencies:

```sh
python -m pip install -r requirements-dev.txt
python launcher.py
```

Verification:

```sh
PYTHONPATH=src python -m pytest -q
python launcher.py --self-test
node --check browser_extension/background.js
gradle -p android testDebugUnitTest assembleDebug lintDebug
```

Android needs Java 17, SDK 35 and Gradle 8.9. Its release version 1.4 updates
1.3 Release with the same signing key. A previous Debug installation has a
different certificate and must be removed once to install Release.

Automated tests include live local HTTPS, authorization, certificate pinning,
address fallback, duplicate prevention, file safety and UI startup/pairing flows.
They do not replace physical Android camera, real Windows input or the owner's
router/mobile-data checks. No live access to the owner's computer is established
by distributing source or an APK.
