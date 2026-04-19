# FAQ: Deploying with Coolify

This document covers lessons learned deploying the `reolink-light-web-monitor` application
using [Coolify](https://coolify.io/) on a local home server. It is intended as a reference
for future deployments of this and similar Python/Flask applications.

---

## What is Coolify?

Coolify is a self-hosted deployment platform that manages Docker containers under the hood,
without requiring you to write Dockerfiles or manage containers manually. It provides a web UI
to deploy, monitor, and manage applications — similar to a self-hosted Heroku or Vercel.

---

## Hardware & Server Setup

**Q: Can Coolify run on the same server as MariaDB?**

Yes. Coolify and MariaDB coexist without issues on a single machine. For a home server
running a handful of personal apps, this is a perfectly sensible setup. The main
considerations are:

- **RAM**: 8GB workable, 16GB comfortable when running several apps simultaneously.
- **Disk**: SSD recommended for the OS and apps.
- **Network**: Give the server a static IP on your LAN so its address never changes.

---

## Connecting to a Local MariaDB Server

**Q: Can apps deployed in Coolify access a MariaDB instance on another server on the LAN?**

Yes. Since Coolify runs apps inside Docker containers, use the **LAN IP address** of the
MariaDB server in your connection string — not `localhost`, as that refers to the container
itself.

Example connection string:
```
mysql+pymysql://myuser:password@192.168.1.x:3306/mydb
```

On the MariaDB server you will also need to:

1. Set `bind-address` to the server's LAN IP or `0.0.0.0` in `/etc/mysql/mariadb.conf.d/50-server.cnf`.
2. Grant access to the app's database user from the Coolify server's IP:
   ```sql
   GRANT ALL ON mydb.* TO 'myuser'@'192.168.1.50' IDENTIFIED BY 'password';
   FLUSH PRIVILEGES;
   ```
3. Allow port `3306` through the MariaDB server's firewall from the Coolify server's IP.

---

## Deploying a Python/Flask App

**Q: What build pack should I use for a Python/Flask app?**

Select **Nixpacks** in Coolify. It auto-detects Python from your `requirements.txt` and
builds without a Dockerfile.

**Q: Do I need to write a Dockerfile?**

No — Nixpacks handles this automatically, provided you have a `nixpacks.toml` file in the
root of your repository (see below).

---

## The nixpacks.toml File

A `nixpacks.toml` file in the repository root controls how Nixpacks builds the app.
This is required when your app depends on system packages not in `requirements.txt`
(such as FFmpeg).

### Final working configuration

```toml
[phases.setup]
nixPkgs = ["ffmpeg", "python311"]

[phases.install]
cmds = [
  "python -m venv /opt/venv",
  "/opt/venv/bin/pip install -r requirements.txt"
]

[start]
cmd = "/opt/venv/bin/python ./backend/server.py"
```

Place this file in the **root of the repository**, not inside the `backend` folder.

### Why a virtual environment?

Nix does not wire up `pip` automatically when using `python311Packages.pip`. Creating
an explicit virtual environment (`/opt/venv`) and using its own `pip` and `python`
binaries is the most reliable approach.

### Errors encountered and fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `exit code: 127` on `pip install` | `pip` not found in PATH | Added venv creation step |
| `No module named pip` | Nix pip package not wiring correctly | Switched to `python -m venv` approach |

---

## Handling Secrets and the .env File

**Q: My app uses a `.env` file for camera credentials. Should I commit it to the repo?**

**No.** Never commit `.env` files containing passwords or sensitive configuration to a
repository. Instead, use Coolify's built-in **Environment Variables** section.

**Q: How do I replicate my `.env` file in Coolify?**

In the Coolify app dashboard, go to the **Environment Variables** tab and add each
variable individually. Coolify stores them securely and injects them into the container
at runtime — exactly as if the `.env` file were present.

If your app uses `python-dotenv`, it falls back gracefully to reading from the real
environment when no `.env` file is found. To be explicit and ensure Coolify variables
always take priority:

```python
from dotenv import load_dotenv
load_dotenv(override=False)  # real env vars take priority over any .env file
```

---

## Network Port Mappings

**Q: How do I access my app from other computers on the LAN?**

In the Coolify app's **General** tab, configure **Network Port Mappings** to expose the
container port to the host. The format is:

```
HOST_PORT:CONTAINER_PORT
```

For this Flask app (which listens internally on port 5000), the mapping used was:

```
3000:5000
```

This means:
- **5000** — Flask's internal port inside the container
- **3000** — the port exposed on the host server, reachable from the LAN

From any computer on the local network, access the app at:

```
http://192.168.x.x:3000
```

Where `192.168.x.x` is the static LAN IP of the Coolify server.

**Q: How do I deploy multiple apps without port conflicts?**

Each app can use the same internal container port (e.g. 5000), but must be mapped to a
different host port. For example:

```
3000:5000  → reolink camera monitor
3001:5000  → energy dashboard
3002:5000  → another app
```

---

## Optional: Accessing Apps by Name Instead of Port

Instead of remembering `192.168.x.x:3000`, you can set up local name-based routing using
**Nginx Proxy Manager** (runs as a Docker container alongside Coolify). This lets you
define local addresses like `cameras.local` that route to the correct port automatically.

This requires a local DNS setup (e.g. Pi-hole) or manual `hosts` file entries on each
client computer.

---

## Summary Checklist for Future Deployments

- [ ] Add `nixpacks.toml` to repo root (include any system dependencies like `ffmpeg`)
- [ ] Use a venv in `nixpacks.toml` to avoid Nix pip issues
- [ ] Set start command to use `/opt/venv/bin/python`
- [ ] Never commit `.env` files — use Coolify Environment Variables instead
- [ ] Set Network Port Mappings in Coolify General tab (`HOST_PORT:5000`)
- [ ] Give the Coolify server a static LAN IP
- [ ] Access app via `http://SERVER_IP:HOST_PORT` from any LAN computer