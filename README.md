# Your Assistant Agent 5.2.0

A personal Windows assistant with its own Android 1.7.0 companion, shared branding,
remote desktop, file transfers and reviewed GitHub/Facebook tools.

[Arabic 5.2 general-control guide](README_V520_AR.md). Generic computer tools now
discover and launch observed Start-menu applications, open folders, create
directories, copy/move files and extract ZIPs. Arbitrary valid domains and web
searches work without adding a website-specific alias. All tools use the
existing owner-approved task and shared-file permissions. Android remains1.7.0.

[Arabic 5.1 update guide](README_V510_AR.md). Phone Facebook requests now use the
same managed account profile as page reads and publishing previews. Plain site
opens execute directly, desktop follow-ups retain bounded task context, QR scans
use portrait orientation, and reviewed ZIP uploads discover matching local
checkouts and retain extracted source on the actual Windows Desktop.

## Facebook planning patch

[Arabic update instructions](README_V501_AR.md). Page search and post reads now pass the read-only execution boundary. Malformed group limits can be corrected by the planner, complete tool exchanges survive context compaction, and tool output receives a sufficient reasoning budget with a bounded retry. Invalid or incomplete tool JSON is rejected before execution. Phone connection settings include a model-independent diagnostics report with safe error codes.

## Windows control and phone dictation

[Read the Arabic 5.0 setup guide](README_V500_AR.md). Update both Windows and
Android. Pair phone QR includes an explicit **Enable full desktop access and
show QR** button enabling screen/input, all local drives, computer AI and the
existing AC sleep guard. Permissions remain opt-in.

Arabic close/switch/open requests reach the computer route. Exact URL and
current-tab/window operations work independently of UIA text or model routing.
The planner can list, focus, close, minimize and maximize observed windows and
select/close observed browser tabs. It can use window tools when page
accessibility is unavailable. Close is graceful: an unsaved-work prompt may
remain for the owner to handle from the phone. The phone also has direct window
selection and close-tab/window controls.

Phone dictation records up to 60 seconds in the foreground, sends AAC through
the paired HTTPS connection to Windows, and uses the existing Groq Whisper
account on the PC. The result fills an editable composer; it is never sent as a
task automatically. Audio files are deleted after processing or cancellation;
stale interrupted captures are cleaned on later startup. The phone holds no
Groq key. Leaving the screen cancels an active recording.

Android includes the 1.5.1 QR runtime dependency fix and camera-activity
lifecycle regression tests. No physical phone, owner's account or Windows
desktop has been validated from this Linux workspace.

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

[Earlier Arabic and Facebook changes](README_V490_AR.md). Native Windows
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
artifact **YourAssistantAgent-Windows-Setup-v5.2.0** and Android Debug. Private
Android signing secrets additionally enable **YourAssistantAgent-Android-Release-v1.7.0**.
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

Android needs Java 17, SDK 35 and Gradle 8.9. Release 1.7.0 uses the existing
release signing key. Use the matching debug-upgrade APK if your installed app
was signed with the earlier debug certificate.

Automated tests include live local HTTPS, authorization, certificate pinning,
address fallback, duplicate prevention, file safety and UI startup/pairing flows.
They do not replace physical Android camera, real Windows input or the owner's
router/mobile-data checks. No live access to the owner's computer is established
by distributing source or an APK.
