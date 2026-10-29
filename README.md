# Your Assistant Agent

A Windows desktop assistant written in Python with a Tkinter interface. The current
application uses **GroqCloud (`openai/gpt-oss-120b`)** for chat and tool calling.
It does not bundle or run the Qwen model described in earlier releases.

## Run from source

Requires Python 3.11 or 3.12, a desktop display, and a Groq API key configured in
the application's settings.

```powershell
python -m pip install -r requirements.txt
python launcher.py
```

An installed `your-assistant-agent` command and `python -m yaa_lite.main` use the
same application initialization as the launcher and packaged Windows executable.
For the module command, install the package or set `PYTHONPATH` to `src` first.

## ZIP updates to GitHub

1. Attach a ZIP in the chat and choose **ZIP → GitHub**, or write
   `ارفع ملف ZIP على جيت هب`.
2. Select the existing local checkout of `maenish-ai/YourAssistantAgent`. It must
   have a clean working tree and the correct `origin` remote.
3. Review the file list and destination branch, then approve the upload.

The app checks and extracts the ZIP contents into that checkout, stages the
reviewed changes, creates a commit, and pushes it using Git. It does not automate
GitHub Desktop's buttons. A GitHub-downloaded `YourAssistantAgent-main` wrapper
folder is removed automatically. Existing project files absent from the ZIP are
not deleted.

Git must be installed (the app can also find Git bundled with GitHub Desktop).
Git author identity and command-line push authentication must be configured.
**A GitHub Desktop sign-in alone does not guarantee that command-line Git can
push.** If pushing fails, the app reports that the commit remains local; use
GitHub Desktop to resolve authentication or network issues. Reattach the same
ZIP to review and retry the pending push without creating a duplicate commit.

## Browser and Facebook setup

For the extension connection:

1. Start the desktop assistant.
2. Open `chrome://extensions` or `edge://extensions`, enable Developer Mode,
   choose **Load unpacked**, and select the `browser_extension` directory.
3. Sign in to Facebook in that same browser, then ask the assistant to verify the
   connection and refresh joined groups.

The extension talks to `127.0.0.1:8765` on the **same computer**. It is not a
remote access server. After updating extension files, reload the extension from
the browser's extensions page.

Facebook publishing currently uses a **separate Playwright browser profile**.
A connected extension does not prove that this publishing profile is signed in.
The app opens the publishing browser when needed; finish its manual sign-in
before running a campaign. Captchas, two-factor authentication and account
checkpoints remain manual. Review and approve the campaign before publishing.

Group discovery and posting depend on Facebook's current page layout and account
permissions. Automated tests do not establish successful posting to a live group.

## Using a phone away from home

There is currently **no Android client or remote command/file transport**.
The Telegram connector is a placeholder, not a running bot. The desktop app's
attachment chooser receives local files only. Sending a ZIP from a phone to the
home computer requires a separate authenticated transport and remote approval
flow; these local repairs do not add that capability.

## Validation and Windows builds

```powershell
python -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "$PWD\src"
python -m pytest -q
python launcher.py --self-test
node --check browser_extension/background.js
```

`.github/workflows/build-windows.yml` runs tests, packages the Windows app with
PyInstaller, smoke-tests the executable, and builds an Inno Setup installer when
changes are pushed to `main`. Download the installer from that run's artifacts;
updating source files does not update an already-installed copy automatically.
The artifact label still contains an older release name.
