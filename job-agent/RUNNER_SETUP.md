# Self-Hosted Runner + Dashboard Setup

One-time setup (~20 minutes). After this the agent runs automatically every 5 hours
on your machine with your residential IP. You never touch it again.

---

## 1. Self-Hosted GitHub Actions Runner

### Download and configure

Go to: **GitHub → your repo → Settings → Actions → Runners → New self-hosted runner**
Select your OS, then run the commands shown. They look like this:

```bash
mkdir ~/actions-runner && cd ~/actions-runner
# macOS
curl -o actions-runner-osx-x64.tar.gz -L https://github.com/actions/runner/releases/download/v2.x.x/actions-runner-osx-x64-2.x.x.tar.gz
tar xzf ./actions-runner-osx-x64.tar.gz

# Linux
curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/download/v2.x.x/actions-runner-linux-x64-2.x.x.tar.gz
tar xzf ./actions-runner-linux-x64.tar.gz

./config.sh --url https://github.com/aadarsh-praveen/resume --token <TOKEN_FROM_GITHUB>
```

### Install as a boot service (runs on every startup)

```bash
# macOS / Linux
sudo ./svc.sh install
sudo ./svc.sh start

# Check status
sudo ./svc.sh status
```

That's it. The runner starts silently on every boot and picks up scheduled workflows automatically.

### Add secrets to GitHub

Go to: **GitHub → repo → Settings → Secrets and variables → Actions → New repository secret**

Add these secrets:

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Claude API key |
| `TELEGRAM_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `HUNTER_API_KEY` | Hunter.io API key |
| `GMAIL_CREDENTIALS_JSON` | Contents of your Gmail credentials JSON file |
| `SHEETS_CREDENTIALS_JSON` | Contents of your Google Sheets credentials JSON |
| `SHEETS_SPREADSHEET_ID` | Google Sheets spreadsheet ID |
| `GITHUB_DASHBOARD_TOKEN` | Personal access token with `workflow` scope (for manual run button) |

---

## 2. FastAPI Dashboard

### Install dashboard dependencies

```bash
cd job-agent
pip install fastapi uvicorn[standard] jinja2
```

### Run the dashboard

```bash
cd job-agent
uvicorn dashboard.main:app --host 0.0.0.0 --port 8000 --reload
```

Access it at: `http://localhost:8000`

### Run on startup (optional)

**macOS** — add to `~/Library/LaunchAgents/com.resume-agent.dashboard.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.resume-agent.dashboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/uvicorn</string>
        <string>dashboard.main:app</string>
        <string>--host</string><string>0.0.0.0</string>
        <string>--port</string><string>8000</string>
    </array>
    <key>WorkingDirectory</key><string>/path/to/Resume/job-agent</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
```
Then: `launchctl load ~/Library/LaunchAgents/com.resume-agent.dashboard.plist`

**Linux** — create `/etc/systemd/system/resume-dashboard.service`:
```ini
[Unit]
Description=Resume Agent Dashboard
After=network.target

[Service]
User=youruser
WorkingDirectory=/path/to/Resume/job-agent
ExecStart=/usr/local/bin/uvicorn dashboard.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```
Then: `sudo systemctl enable resume-dashboard && sudo systemctl start resume-dashboard`

---

## 3. Cloudflare Tunnel (Remote Access)

Access your dashboard from any device, anywhere.

```bash
# Install
brew install cloudflared   # macOS
# or: curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared

# Login (opens browser)
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create resume-agent

# Route to your domain (optional — can use the auto-generated *.trycloudflare.com URL instead)
cloudflared tunnel route dns resume-agent agent.yourdomain.com

# Run tunnel pointing to local dashboard
cloudflared tunnel run --url http://localhost:8000 resume-agent
```

For a quick test without a domain (no account needed):
```bash
cloudflared tunnel --url http://localhost:8000
# Outputs: https://random-name.trycloudflare.com
```

### Install Cloudflare tunnel as a boot service

```bash
sudo cloudflared service install
sudo systemctl start cloudflared   # Linux
# or: sudo launchctl start com.cloudflare.cloudflared  # macOS
```

---

## 4. Applicant Profile (.env)

Add these to your `job-agent/.env` file:

```env
# Applicant profile (used for auto-apply)
APPLICANT_FIRST_NAME=Aadarsh
APPLICANT_LAST_NAME=Praveen
APPLICANT_EMAIL=your@email.com
APPLICANT_PHONE=+1-555-000-0000
APPLICANT_LINKEDIN_URL=https://linkedin.com/in/yourprofile
APPLICANT_PORTFOLIO_URL=https://yourwebsite.com   # optional

# Dashboard
GITHUB_DASHBOARD_TOKEN=ghp_xxxx   # PAT with workflow scope, for manual run button
GITHUB_REPO=aadarsh-praveen/resume
```
