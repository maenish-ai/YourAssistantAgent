# Your Assistant Agent 4.4

A Python/Tkinter Windows assistant with a standalone native Android companion.
GroqCloud (`openai/gpt-oss-120b`) handles conversation and tool selection; local
application tools perform reviewed GitHub and Facebook tasks.

## Windows setup

Install Python 3.11 or 3.12 and configure your Groq key in the desktop app:

```powershell
python -m pip install -r requirements.txt
python launcher.py
```

The launcher, installed `your-assistant-agent` command, module entrypoint and
packaged Windows executable share the same initialization.

## GitHub ZIP uploads

In **Settings → Android & GitHub**, set the target repository (`owner/name`) and
its existing local Git checkout. The target persists across chats. Git author
identity and command-line push authentication must be configured; signing in to
GitHub Desktop alone does not guarantee Git can push from the command line.

Attach a ZIP from desktop chat or Android. The assistant checks it and displays
its target repository, branch and changes. Only the approval button writes files,
commits and pushes. Missing files are not deleted. ZIP wrappers for the target
repository are removed automatically. Failed pushes leave a local commit and
can be retried through a new preview without creating a duplicate commit.

The app can target different configured GitHub repositories. It does not create
GitHub repositories or automatically clone a checkout, and the model cannot
change the configured destination. Choose/create your checkout with GitHub
Desktop before using remote uploads.

## Android companion

The source is in [`android/`](android/). It uses native Java views, an encrypted
Android Keystore pairing token, HTTPS, ZIP attachments, event polling and explicit
approve/cancel controls. Android 8.0 or later is required. It is independent of
Telegram; no Telegram bot is involved.

See [the Arabic setup guide](README_V440_AR.md) for the complete procedure.

1. In the unlocked desktop app, open **Settings → Android & GitHub**, generate a
   pairing token, enable Android connection and save.
2. Expose the loopback companion (`127.0.0.1:8766` by default) using an authenticated
   private network with a valid HTTPS endpoint. For example, install Tailscale
   on Windows and Android, sign in to the same tailnet, and configure on Windows:

   ```powershell
   tailscale serve --bg http://127.0.0.1:8766
   ```

   Follow Tailscale's displayed setup and HTTPS requirements. Use the HTTPS URL
   it reports, not `127.0.0.1`, in the phone app. Tailscale must remain connected
   on both devices. Do not use Funnel/public exposure for this setup.
3. Install the Android debug APK from the build artifacts, enter that HTTPS URL
   and the desktop pairing token, and tap Connect.

The app listens only on loopback and provides no public relay. HTTPS/private
network configuration is a required setup step, not automatic. Both the Windows
assistant and home computer must remain running and awake. Unlock the assistant
after restart before remote access works. Android polls while the app is open;
this release does not provide background push notifications.

Remote ZIPs are limited to 20 MiB. Files stay on the computer and are not sent to
the model. The configured conversation service still sends chat text to Groq.
Approvals expire after at most 15 minutes, are bound to a particular preview,
and work once. A new instruction invalidates the old approval. A lost network
reply is not proof that a request failed; inspect the conversation before
repeating it. `/new`, `/cancel`, `/status` are available in Android chat.
Changing the pairing token revokes the old connection; changing settings or
restarting the desktop app invalidates outstanding approval buttons.

## Facebook

Load `browser_extension` unpacked in Chrome/Edge, sign in to Facebook, and reload
the extension after updates. The extension uses loopback port 8765 for connection
checks and joined-group discovery.

Publishing uses a **separate managed Playwright profile**. Ask
`افتح متصفح النشر لفيسبوك` and complete sign-in there on the computer during
initial setup. An extension connection alone does not establish publishing access.
Passwords, CAPTCHA, two-factor authentication and checkpoints remain manual.

Ask to refresh/select groups by keywords or exclusions, then prepare sharing
one to four recent visible page posts. Before approval, the assistant resolves
and shows the **actual post links and all target groups**. Execution uses those
exact links and groups, even if the page or group list later changes. It reports
published, submitted, pending group approval, skipped and failed outcomes separately.

Unscheduled requests default to one execution after approval. A configured
recurring schedule reuses the approved links; new posts need a new preview.
The finder follows visible page links, not a verified chronological feed or
Meta Ads Manager. Review the displayed links. Account permissions and Facebook's
current page layout affect live behavior.

## Tests and builds

```powershell
python -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "$PWD\src"
python -m pytest -q
python launcher.py --self-test
node --check browser_extension/background.js
```

For Android with Gradle 8.9 and Android SDK 35 installed:

```sh
gradle -p android :app:testDebugUnitTest :app:assembleDebug
```

The single `.github/workflows/build-windows.yml` workflow tests and builds both
the Windows installer and Android debug APK for `main` pushes and pull requests.
Source changes do not update existing Windows installations automatically.
Debug APKs are for testing; release signing and distribution are not configured.
