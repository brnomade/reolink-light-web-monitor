module.exports = {
  apps: [{
    name: "security-monitor",
    script: "/home/andre/Coding/reolink-light-web-monitor/backend/server.py",
    interpreter: "/home/andre/Coding/reolink-light-web-monitor/venv/bin/python",
    cwd: "/home/andre/Coding/reolink-light-web-monitor",
    env_file: ".env"
  }]
}
