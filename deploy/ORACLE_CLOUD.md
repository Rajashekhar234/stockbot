# Oracle Cloud Free Tier Deployment

The Free Tier gives you an **Always-Free Ampere A1 VM** (4 vCPU / 24 GB RAM) — far more than this bot needs. These steps assume Ubuntu 22.04 ARM.

## 1. Provision the VM

1. Sign in to https://cloud.oracle.com → **Compute → Instances → Create instance**.
2. Image: **Canonical Ubuntu 22.04** (ARM build).
3. Shape: **VM.Standard.A1.Flex**, 1 OCPU / 6 GB RAM (well within Always-Free).
4. Networking: keep the default VCN, **assign public IPv4**.
5. Add your SSH public key, click **Create**.
6. Wait ~1 minute, copy the public IP.

## 2. Open egress (no inbound needed)

Telegram is **outbound long-poll** — no port forward, no webhook. The default Oracle security list already allows all egress. Nothing to configure.

## 3. SSH in and install

```bash
ssh ubuntu@<public-ip>

sudo apt update && sudo apt install -y python3.11 python3.11-venv git tzdata
sudo timedatectl set-timezone Asia/Kolkata

git clone <your-repo-url> stockbot     # or: scp the folder up
cd stockbot
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env        # paste Angel One + Gemini + Telegram values
mkdir -p logs
```

## 4. Install as a service

```bash
sudo cp deploy/stockbot.service /etc/systemd/system/stockbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now stockbot
sudo systemctl status stockbot
journalctl -u stockbot -f          # live logs
```

The service runs `python main.py --schedule` and triggers itself every weekday at **08:55 IST**.

## 5. Telegram setup

1. Talk to **@BotFather** → `/newbot` → copy the token → put in `TELEGRAM_BOT_TOKEN`.
2. Talk to **@userinfobot** → it replies with your user id → put in `TELEGRAM_ADMIN_IDS`.
3. Start a chat with your new bot and send any message → grab `chat.id` from
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → put in `TELEGRAM_CHAT_ID`.
4. Restart the service: `sudo systemctl restart stockbot`.
5. From your phone, send **`/help`** to your bot.

### Available commands

| Command | Effect |
|---|---|
| `/status` | Mode, paused state, capital config, open position count |
| `/pause` | Block any new entries (existing trade still managed) |
| `/resume` | Re-enable new entries |
| `/positions` | List open positions with SL/TGT |
| `/stop` | Graceful shutdown after current trade closes |

> Only user IDs listed in `TELEGRAM_ADMIN_IDS` can issue commands. Others get "Unauthorized."

## 6. "Don't trade today"

Two ways:
- **Before 08:55 IST**: send `/pause` from Telegram. Bot will start, build universe, and skip entries.
- **After bot is running**: send `/pause` any time. Already-open trades still hit SL/Target.

## 7. Updating

```bash
ssh ubuntu@<public-ip>
cd stockbot
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart stockbot
```

## 8. Cost

Always-Free A1 VM = **₹0/month** indefinitely as long as Oracle keeps the tier alive. No outbound bandwidth charges within the free 10 TB/month.
