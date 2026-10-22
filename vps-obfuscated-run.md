# VPS Setup Guide – TG Ads Bot (Obfuscated / Compiled Backend)

Ei guide-e backend-ta **obfuscated** (compiled `.so`) hisebe VPS-e 24/7 run korbe. Python source (`.py`) kothao thakbe na — shudhu machine-compiled module thakbe, tai keu code porte parbe na. Bakita `systemd + nginx + SSL` diye age-r motoi.

> Telegram webhook-er jonno **HTTPS + ekta domain/subdomain** lagbe (jemon `bot.yourdomain.com`). Domain-er DNS-e ekta **A record** VPS-er IP-te point korun.

---

## 0. Ja lagbe
- Ubuntu 22.04 / 24.04 VPS (1 GB RAM-i jothesto), root access
- Ekta domain/subdomain → VPS IP (A record)
- `backend-vps/` folder (ei project-er moddhe ache). Etar bhitore obfuscated `.c` file + `build.sh` + `setup.py` + `requirements-vps.txt` + `.env.example` ache.

> **Guruttopurno:** compiled module Python **3.11**-er jonno banano. Tai VPS-eo Python 3.11 lagbe (nicher Step 1-e deya ache). 3.10 / 3.12 diye build korle module cholbe na.

---

## 1. Server prepare (Python 3.11 + build tools)
```bash
apt update && apt upgrade -y
apt install -y software-properties-common nginx certbot python3-certbot-nginx unzip gcc
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.11 python3.11-venv python3.11-dev
timedatectl set-timezone Asia/Dhaka
python3.11 --version   # Python 3.11.x dekhabe
```

## 2. Code upload `/root/tg-ads-bot`-e
Nijer PC theke zip upload:
```bash
scp source-code.zip root@YOUR_VPS_IP:/root/
```
VPS-e:
```bash
mkdir -p /root/tg-ads-bot
cd /root/tg-ads-bot
unzip -o /root/source-code.zip
ls /root/tg-ads-bot/backend-vps   # *.c, build.sh, setup.py, requirements-vps.txt thakbe
```
Ekhon theke shudhu **`backend-vps/`** folder niye kaj korbo:
```bash
cd /root/tg-ads-bot/backend-vps
```

## 3. Build (`.c` → `.so`)
Ei ekta command-i venv banabe, package install korbe, obfuscated module compile korbe, ar `.c` + `setup.py` muche dibe (jate source aro-o na thake):
```bash
cd /root/tg-ads-bot/backend-vps
bash build.sh
```
Shesh-e emon list dekhabe:
```
Build done. Compiled modules:
admin_panel.cpython-311-...-linux-gnu.so
bot.cpython-311-...-linux-gnu.so
db.cpython-311-...-linux-gnu.so
server.cpython-311-...-linux-gnu.so
... (moth 15 ta)
```
> Build-er por folder-e shudhu `*.so`, `venv/`, `requirements-vps.txt`, `build.sh` thakbe. Kono `.py`/`.c` thakbe na.

## 4. `.env` file
```bash
cp .env.example .env
nano .env
```
`PUBLIC_BASE_URL`-e nijer domain din. Baki value-gulo already bhora ache:
```
CORS_ORIGINS="*"
DATABASE_URL="postgresql://neondb_owner:npg_BCSIVHlF30sr@ep-icy-thunder-ao9zyx1a-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
TELEGRAM_BOT_TOKEN="8880522002:AAGFBfqAN-YCEblw1G0vDrrxxSl576muF7c"
TELEGRAM_WEBHOOK_SECRET="bd8f71c94da6f3df7cdb72eb8845c6a2c24bfa490add0d8b"
PUBLIC_BASE_URL="https://bot.yourdomain.com"
ADMIN_IDS="7188243734"
META_PIXEL_ID=""
META_API_VERSION="v21.0"
META_ACCESS_TOKEN=""
META_TEST_EVENT_CODE=""
START_TOKEN_TTL_MINUTES="30"
```
> VPS-e `DISABLE_WEBHOOK_SETUP` **dibenna** — VPS nijei Telegram webhook set korbe.
```bash
chmod 600 .env
```

## 5. Test run (1 bar)
```bash
cd /root/tg-ads-bot/backend-vps
./venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001
```
`Application startup complete` dekhle `Ctrl+C` diye bondho korun.
(Prothom start-e DB connect hote ~15-20 sec lagte pare. `setWebhook ... -> False` aste pare karon SSL ekhono hoyni — Step 7-er por thik hobe.)

## 6. systemd service (24/7)
```bash
nano /etc/systemd/system/tg-ads-bot.service
```
```ini
[Unit]
Description=TG Ads Bot (Obfuscated FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
User=root
WorkingDirectory=/root/tg-ads-bot/backend-vps
ExecStart=/root/tg-ads-bot/backend-vps/venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```
> `--workers 1` rakhben. Ekadhik worker dile message duplicate hote pare.

```bash
systemctl daemon-reload
systemctl enable --now tg-ads-bot
systemctl status tg-ads-bot
```

## 7. Nginx + SSL (HTTPS)
```bash
nano /etc/nginx/sites-available/tg-ads-bot
```
```nginx
server {
    listen 80;
    server_name bot.yourdomain.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```
```bash
ln -s /etc/nginx/sites-available/tg-ads-bot /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
certbot --nginx -d bot.yourdomain.com --redirect -m you@email.com --agree-tos -n
```
SSL hoye gele bot restart din, jate webhook set hoy:
```bash
systemctl restart tg-ads-bot
journalctl -u tg-ads-bot -n 30 --no-pager | grep setWebhook   # "-> True" dekhabe
```
Firewall chalu thakle:
```bash
ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw enable
```

## 8. Check
```bash
curl https://bot.yourdomain.com/api/
# {"message":"ok"}
curl "https://api.telegram.org/bot8880522002:AAGFBfqAN-YCEblw1G0vDrrxxSl576muF7c/getWebhookInfo"
# "url": "https://bot.yourdomain.com/api/telegram/webhook" dekhabe
```
Telegram-e bot-ke `/start` din — reply aslei shob thik.

---

## Common problems
- **`ModuleNotFoundError: No module named 'server'`** → `WorkingDirectory` thik `backend-vps` folder-e set ache kina dekhun; `.so` file oi folder-ei thakte hobe.
- **Build-e `Python.h: No such file`** → `apt install -y python3.11-dev gcc` den, tarpor abar `bash build.sh`.
- **`.so` import error / wrong version** → VPS-er Python 3.11 kina check korun (`python3.11 --version`). Onno version hole module cholbe na; `venv` muche abar `bash build.sh`.
- **`setWebhook -> False`** → SSL (Step 7) shesh na hole asbe. HTTPS thik hole restart dile `-> True` hobe.
- **Update kora code abar deploy** korte hole: notun `backend-vps/` upload → `rm -rf venv` → `bash build.sh` → `systemctl restart tg-ads-bot`.
