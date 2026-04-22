# FAQ: Deploying Python Apps with PM2

This document covers lessons learned deploying the `reolink-light-web-monitor` application
using [PM2](https://pm2.keymetrics.io/) on a local home server. It is intended as a reference
for future deployments of this and similar Python/Flask applications.

---

## What is PM2?

PM2 is a process manager originally built for Node.js but works well with Python. It runs
your apps as native processes directly on the host OS — no containers, no Docker — giving
you native performance. It handles auto-restart on crash, startup on boot, and centralised
log management across all your apps.

---

## Installation

PM2 requires Node.js. On Ubuntu:

```bash
# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install PM2 globally
sudo npm install -g pm2
```

---

## Setting Up Your Python App

PM2 does not manage Python environments or `requirements.txt` — that is your responsibility
before handing the app to PM2. Do this once on the server:

**1. Clone the repo**
```bash
cd /home/andre/Coding
git clone https://github.com/brnomade/reolink-light-web-monitor.git
```

**2. Create a virtual environment and install dependencies**
```bash
cd reolink-light-web-monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

**3. Install any system dependencies (e.g. FFmpeg)**
```bash
sudo apt install -y ffmpeg
```

**4. Create your .env file on the server**
```bash
nano /home/andre/Coding/reolink-light-web-monitor/.env
```
Paste your camera credentials and save. This file stays on the server only — never commit
it to the repository.

---

## The Ecosystem Config File

Rather than launching apps from the command line, use a PM2 **ecosystem config file**. This
is a `ecosystem.config.js` file placed in the root of your repository.

### Working configuration

```js
module.exports = {
  apps: [{
    name: "security-monitor",
    script: "/home/andre/Coding/reolink-light-web-monitor/backend/server.py",
    interpreter: "/home/andre/Coding/reolink-light-web-monitor/venv/bin/python",
    cwd: "/home/andre/Coding/reolink-light-web-monitor",
    env_file: ".env"
  }]
}
```

### Key points

- **`script`**: Use the **full absolute path** to your Python script — not a relative path
  like `./backend/server.py`. This is critical for the working directory to resolve correctly.
- **`interpreter`**: Point to the **venv's Python binary**, not the system Python. This gives
  PM2 access to all your installed packages.
- **`cwd`**: Set to the **repo root**, not the `backend` subfolder. This ensures relative
  paths in the app (e.g. `frontend/index.html`) resolve correctly.
- **`env_file`**: Points to your `.env` file for camera credentials and other secrets.

---

## Launching the App

```bash
cd /home/andre/Coding/reolink-light-web-monitor
pm2 start ecosystem.config.js
pm2 save                          # persist app list so it survives reboots
```

---

## Critical: Updating the Ecosystem Config

**`pm2 restart` does not fully reload an updated ecosystem config file.** If you make any
changes to `ecosystem.config.js`, you must delete and re-start the app:

```bash
pm2 delete security-monitor
pm2 start ecosystem.config.js
pm2 save
```

Skipping the `delete` step will cause PM2 to keep running the old configuration silently,
making config changes appear to have no effect.

---

## Updating the App After a Git Pull

When you push changes to GitHub and pull them on the server:

```bash
cd /home/andre/Coding/reolink-light-web-monitor
git pull
source venv/bin/activate
pip install -r requirements.txt   # only needed if requirements changed
deactivate
pm2 restart security-monitor
```

If you changed `ecosystem.config.js` as part of the update, use `delete` + `start` instead
of `restart` (see above).

---

## Surviving Reboots

Run these once after your initial setup:

```bash
pm2 startup        # generates a systemd startup command — run the output it gives you
pm2 save           # saves current app list to be restored on boot
```

After any future `delete` + `start` cycle, always run `pm2 save` again to update the
saved app list.

---

## Firewall

If Flask is running but unreachable from other computers on the LAN, check UFW:

```bash
sudo ufw status
```

If active, open the port Flask is listening on:

```bash
sudo ufw allow 5000/tcp
```

Also verify Flask is listening on all interfaces, not just localhost:

```bash
sudo ss -tlnp | grep python
```

You want to see `0.0.0.0:5000` — not `127.0.0.1:5000`. If it shows localhost only, ensure
your `server.py` starts Flask with:

```python
app.run(host="0.0.0.0", port=5000, threaded=True)
```

---

## Handling Secrets

Never commit your `.env` file to the repository. Keep it on the server only and reference
it via the `env_file` field in `ecosystem.config.js`.

If you need to update credentials, edit the `.env` file directly on the server and restart
the app:

```bash
nano /home/andre/Coding/reolink-light-web-monitor/.env
pm2 restart security-monitor
```

---

## Working Directory and Relative Paths

A common source of errors is relative file paths in the app failing because the process
is not launched from the expected directory.

**Symptom:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'frontend/index.html'
```

**Cause:** PM2 is not launching from the repo root, so relative paths like
`frontend/index.html` cannot be resolved.

**Fix — without modifying code:** Use a full absolute path in the `script` field and set
`cwd` to the repo root in `ecosystem.config.js` (as shown above). Always prefer a
configuration fix over a code change when the issue is purely about how the app is launched.

---

## Useful Day to Day Commands

```bash
pm2 list                          # list all running apps and their status
pm2 logs security-monitor         # tail live logs
pm2 logs security-monitor --lines 50  # show last 50 log lines
pm2 restart security-monitor      # restart the app (use for code changes only)
pm2 stop security-monitor         # stop the app
pm2 delete security-monitor       # remove from PM2 (use when changing ecosystem config)
pm2 describe security-monitor     # show full config and runtime details
pm2 monit                         # live terminal dashboard for all apps
```

---

## Deploying Multiple Apps

Each additional Python app gets its own entry in the `apps` array of `ecosystem.config.js`,
or its own separate ecosystem file. Each app should have its own venv and listen on a
different port:

```js
module.exports = {
  apps: [
    {
      name: "security-monitor",
      script: "/home/andre/Coding/reolink-light-web-monitor/backend/server.py",
      interpreter: "/home/andre/Coding/reolink-light-web-monitor/venv/bin/python",
      cwd: "/home/andre/Coding/reolink-light-web-monitor",
      env_file: "/home/andre/Coding/reolink-light-web-monitor/.env"
    },
    {
      name: "energy-dashboard",
      script: "/home/andre/Coding/energy-dashboard/app.py",
      interpreter: "/home/andre/Coding/energy-dashboard/venv/bin/python",
      cwd: "/home/andre/Coding/energy-dashboard",
      env_file: "/home/andre/Coding/energy-dashboard/.env"
    }
  ]
}
```

Access each app via its own port on the server's LAN IP:
```
http://192.168.x.x:5000  → security monitor
http://192.168.x.x:5001  → energy dashboard
```

---

## Summary Checklist for Future Deployments

- [ ] Install Node.js and PM2 globally
- [ ] Clone repo and create venv manually
- [ ] Install requirements via `pip install -r requirements.txt`
- [ ] Install system dependencies (e.g. `sudo apt install -y ffmpeg`)
- [ ] Create `.env` file on server — never commit it to the repo
- [ ] Create `ecosystem.config.js` with full absolute path in `script` field
- [ ] Set `cwd` to repo root in ecosystem config
- [ ] Point `interpreter` to venv Python binary
- [ ] Use `pm2 delete` + `pm2 start` when changing ecosystem config (not just `restart`)
- [ ] Run `pm2 startup` and `pm2 save` to survive reboots
- [ ] Open firewall port with `sudo ufw allow PORT/tcp`
- [ ] Verify Flask listens on `0.0.0.0` not `127.0.0.1`
