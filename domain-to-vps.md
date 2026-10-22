# Domain → VPS Connect Guide (TG Ads Bot)

Domain-ke VPS-er sathe connect kora mane: tomar domain-er DNS-e ekta **A record** boshano, ja VPS-er **IP address**-e point korbe. Niche puro step-by-step deya holo.

> Guide-e subdomain hisebe `bot.yourdomain.com` dhora hoyeche. Tumi nijer domain/subdomain use korbe.

---

## 1. VPS-er public IP ber koro
VPS-e SSH kore:
```bash
curl -s ifconfig.me
```
Ekta IP dibe, jemon `203.0.113.45` — note koro.

## 2. Domain provider-er DNS panel-e jao
Tomar domain jekhane kinecho (Namecheap / GoDaddy / Cloudflare / Hostinger ...) — oikhane login kore **DNS / DNS Management / Nameserver** section-e jao.

## 3. A record add koro
Bot-er jonno ekta subdomain use koro:

| Field               | Value                        |
|---------------------|------------------------------|
| Type                | `A`                          |
| Name / Host         | `bot`  (shudhu subdomain naam)|
| Value / Points to   | tomar VPS IP (`203.0.113.45`)|
| TTL                 | `Automatic` / `3600`         |

> - Full domain (`yourdomain.com`) nijei use korle Name field-e `@` dibe.
> - **Cloudflare** use korle proxy (orange cloud) **OFF** rakho (DNS only / grey cloud), na hole certbot/SSL-e jhamela hobe.

## 4. DNS propagate hote dao
2–30 min (max 24 ghonta) lagte pare. Check koro:
```bash
dig +short bot.yourdomain.com
# ba
ping bot.yourdomain.com
```
Tomar VPS IP dekhালে → DNS thik ache.

## 5. `.env`-e domain boshao
`backend-vps/.env`-e:
```
PUBLIC_BASE_URL="https://bot.yourdomain.com"
```
(DNS-e je subdomain diyecho, thik seta-i.)

## 6. Nginx + SSL (HTTPS)

> `nano`-te config paste korle majhe majhe thik moto save hoy na, ar certbot `Could not find a matching server block` error dey. Tai niche **`cat` diye direct file lekha** holo — eta nirapod.

**6a. Nginx config file lekho** (puro block ek sathe paste koro; `bot.yourdomain.com` nijer domain diye bodলe dao):
```bash
cat > /etc/nginx/sites-available/tg-ads-bot << 'EOF'
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
EOF
```

**6b. Confirm file-e thik moto lekha hoyeche:**
```bash
cat /etc/nginx/sites-available/tg-ads-bot
```
(Upor-er server block-ta dekhabe. Khali asle 6a abar koro.)

**6c. Enable + reload** (`ln -sf` use koro — age symlink thakleও error dibe na):
```bash
ln -sf /etc/nginx/sites-available/tg-ads-bot /etc/nginx/sites-enabled/tg-ads-bot
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

**6d. SSL certificate nao:**
```bash
certbot --nginx -d bot.yourdomain.com --redirect -m you@email.com --agree-tos -n
```

> **Jodi certbot bole "certificate was saved, but could not be installed" / "Could not find a matching server block"** — mane cert peye gecho, shudhu install hoyni (sadharonot config file khali chilo). 6a-6c thik kore niচের command diye install koro:
> ```bash
> certbot install --cert-name bot.yourdomain.com
> ```

## 7. Bot restart → webhook set
```bash
systemctl restart tg-ads-bot
journalctl -u tg-ads-bot -n 30 --no-pager | grep setWebhook   # "-> True" dekhabe
```

## 8. Check
```bash
curl https://bot.yourdomain.com/api/
# {"message":"ok"}
```
Telegram-e bot-ke `/start` dao — reply aslei shob thik.

---

## Short e flow
VPS IP ber koro → domain DNS-e `A record` (bot → IP) → propagate hoy → `.env`-e `PUBLIC_BASE_URL` set koro → nginx + certbot SSL → bot restart → webhook `-> True`.

> **Guruttopurno:** certbot/SSL neওয়ার aগে DNS obosshoi VPS IP-te point korte hobe, na hole certificate issue hobe na. **Age DNS, pore SSL.**

## Common problems
- **certbot: `certificate was saved, but could not be installed` / `Could not find a matching server block`** → cert peye gecho, kintu nginx config file (`/etc/nginx/sites-available/tg-ads-bot`) khali ba `server_name` thik nei. Step **6a-6c** (`cat > ...` diye file lekho, `cat`-e confirm koro, `ln -sf` + reload) koro, tarpor `certbot install --cert-name bot.yourdomain.com`.
- **`ln: failed to create symbolic link ... File exists`** → harmless. `ln -s`-er bodole `ln -sf` use koro (force, age thakleও cholbe).
- **`dig`-e IP ascche na / bhul IP** → DNS ekhono propagate hoyni ba A record bhul. Record thik koro, 10-30 min opekkha koro. Taratari check: `dig +short bot.yourdomain.com @ns1.dnsowl.com` (authoritative NS-ke direct jiggesh — propagation cache baদ).
- **certbot fail (`DNS problem` / `challenge failed`)** → `bot.yourdomain.com` ekhono VPS IP-te point korche na, ba Cloudflare proxy ON ache. DNS thik kore abar certbot chalao.
- **`curl https://bot.yourdomain.com/api/` timeout** → firewall. `ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw enable`.
- **webhook `-> False`** → SSL thik moto hoyni ba `PUBLIC_BASE_URL` bhul. Thik kore `systemctl restart tg-ads-bot`.
