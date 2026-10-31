# Personal encrypted relay

This is an opaque HTTPS mailbox for the paired Android/Windows application.
It requires a real hosted endpoint. It is not already deployed by this source.

For a VPS with Docker Compose and a domain pointing to it:

```sh
cd relay_server
python3 setup.py --domain relay.your-domain.example
docker compose up -d --build
```

Import the generated private `desktop-setup.json` into Windows Settings →
Automatic QR pairing. Both generated setup files are ignored by Git. Never
include them in source bundles. The server prints no enrollment credentials.

Caddy terminates HTTPS; the Python broker is reachable only inside the Compose
network. The broker uses only the Python standard library. It routes opaque
AES-GCM envelopes and has no pairing/decryption key. It retains bounded queues
and responses in memory, expiring them after 90 seconds. Run one process/replica;
the desktop reconnects and re-registers after restarts. Keep the enrollment key
stable across restarts. Maximum 32 channels, 32 pending requests per channel,
64 concurrent request threads and 4 MiB encrypted envelopes.

Native Python hosting can start `python relay_server/server.py`, set
`RELAY_BIND=0.0.0.0`, provide `PORT` and a strong secret `RELAY_ENROLLMENT_KEY`, and
use `/health`. HTTPS must be supplied by the hosting provider. Review the
provider's uptime, plan costs and egress allowances before deployment.

See `README_V460_AR.md` for owner setup, Android scanning and limits.
