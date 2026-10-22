# VPS Setup Guide – TG Ads Bot (Backend 24/7)

Bot backend VPS-e `/root/tg-ads-bot` folder-e run hobe. `systemd` diye 24/7 cholbe (crash ba VPS reboot holeo nije abar chalu hobe), ar `nginx + SSL` diye Telegram webhook HTTPS-e asbe.

> Telegram webhook-er jonno **HTTPS + ekta domain/subdomain** lagbe (jemon `bot.yourdomain.com`). Domain-er DNS-e ekta **A record** VPS-er IP-te point korun.

---

## 0. Ja lagbe
- Ubuntu 22.04 / 24.04 VPS (1 GB RAM-i jothesto), root access
- Ekta domain/subdomain → VPS IP (A record)
- Project code (Emergent theke **Download Code**, ba website-er `/download` page theke zip)

---

## 1. Server prepare
```bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx unzip
timedatectl set-timezone Asia/Dhaka
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
ls /root/tg-ads-bot/backend   # server.py, bot.py, db.py ... thakbe
```
Final structure:
```
/root/tg-ads-bot/
├── backend/        <- bot (eta run hobe)
└── frontend/       <- website (optional)
```

## 3. Python environment
```bash
cd /root/tg-ads-bot/backend
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements-vps.txt
```
> `requirements.txt` na, **`requirements-vps.txt`** use korben. Etate shudhu bot-er dorkari package ache.

## 4. `.env` file
```bash
nano /root/tg-ads-bot/backend/.env
```
Nicher lekha paste korun. `bot.yourdomain.com` er jaygay nijer domain din:
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
> VPS-e `DISABLE_WEBHOOK_SETUP` **dibenna**. VPS nijei Telegram webhook set korbe.
```bash
chmod 600 /root/tg-ads-bot/backend/.env
```

## 5. Test run (1 bar)
```bash
cd /root/tg-ads-bot/backend
./venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001
```
`Application startup complete` dekhle `Ctrl+C` diye bondho korun.
(Ekhon `setWebhook ... -> False` aste pare, karon SSL ekhono set kora hoyni. Step 7-er por thik hoye jabe.)

## 6. systemd service (24/7)
```bash
nano /etc/systemd/system/tg-ads-bot.service
```
```ini
[Unit]
Description=TG Ads Bot (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
User=root
WorkingDirectory=/root/tg-ads-bot/backend
ExecStart=/root/tg-ads-bot/backend/venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
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
journalctl -u tg-ads-bot -n 20 --no-pager | grep setWebhook   # "-> True" dekhabe
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
# "url":"https://bot.yourdomain.com/api/telegram/webhook" dekhabe
```
Telegram-e bot-ke `/start` ar `/admin` diye test korun.

---

## Website (frontend) niye
- Website Emergent-e thakleo cholbe. Website ar VPS bot **eki Neon database** use kore, tai ad tracking ar join link match thik thakbe.
- Emergent preview-er backend-e `DISABLE_WEBHOOK_SETUP="true"` set kora ache. Tai preview restart holeo Telegram webhook VPS theke soriye nibe na.
- Website-o VPS-e nite chaile:
  ```bash
  apt install -y nodejs npm && npm i -g yarn
  cd /root/tg-ads-bot/frontend
  echo 'REACT_APP_BACKEND_URL=https://bot.yourdomain.com' > .env
  echo 'GENERATE_SOURCEMAP=false' >> .env
  yarn install && yarn build
  ```
  Tarpor nginx server block-e eta add korun (`location /api/` er upore):
  ```nginx
      root /root/tg-ads-bot/frontend/build;
      location / { try_files $uri /index.html; }
  ```
  `chmod 755 /root /root/tg-ads-bot /root/tg-ads-bot/frontend` diye `systemctl reload nginx` din.

---

## Dorkari command
| Kaj | Command |
|---|---|
| Status | `systemctl status tg-ads-bot` |
| Live log | `journalctl -u tg-ads-bot -f` |
| Restart | `systemctl restart tg-ads-bot` |
| Stop | `systemctl stop tg-ads-bot` |
| Code update | notun zip unzip → `systemctl restart tg-ads-bot` |
| SSL renew test | `certbot renew --dry-run` (auto renew hoy) |

## Somossha holo
- **Bot reply dey na:** `getWebhookInfo` check korun. `last_error_message` dekhun, ar `journalctl -u tg-ads-bot -n 100` dekhun.
- **`KeyError: 'XYZ'`:** `.env`-e oi key nei. Step 4 abar dekhun.
- **Database error:** `DATABASE_URL` thik ache kina, ar Neon project active kina check korun.
- **Webhook onno jaygay chole geche:** `systemctl restart tg-ads-bot`. Restart-er somoy VPS abar nijer URL set kore.
