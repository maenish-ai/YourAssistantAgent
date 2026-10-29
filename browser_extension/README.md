# Your Assistant Agent Browser Bridge v2.0.1

This optional extension connects **the normal browser you already use** to Your Assistant Agent through `127.0.0.1:8765` only. Keep the desktop app running on the same computer.

For Chrome/Edge: open the extensions page (`chrome://extensions` or `edge://extensions`), enable Developer Mode, choose **Load unpacked**, and select this `browser_extension` folder. After updating these files, click **Reload** on the extension card; if the browser asks for the new alarms permission, accept it to enable reconnection. Click the extension icon to request an immediate connection check.

The worker uses browser alarms to reconnect after suspension. Commands run one at a time, and expired commands do not start later. A Facebook connection check inspects a temporary Facebook tab for signed-in UI, login prompts, or security checkpoints, then closes it. A successful HTTP response alone is not proof of a signed-in account.

The bridge supports opening pages, inspecting/interacting with the active tab, and discovering joined Facebook groups. Facebook campaign publishing currently uses the app's **separate managed browser profile**, which must also be signed in; signing in through this extension does not copy cookies or authenticate that profile.

This extension does not provide remote Android access or expose the computer to the internet. It does not bypass CAPTCHA, security checkpoints, or browser permission prompts. Final publishing actions remain subject to the app's approval policy.
