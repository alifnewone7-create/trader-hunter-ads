# Vercel Setup Guide – Frontend (Website)

`frontend/vercel.json` file-e install command, build command ar output folder **age thekei set kora ache**. Tai Vercel nije-i egulo use korbe, apnake kichu type korte hobe na.

---

## 1. Vercel project settings

| Setting | Value |
|---|---|
| **Root Directory** | `frontend`  ← (eta obosshoi set korben) |
| **Framework Preset** | `Other` |
| **Install Command** | `yarn install --frozen-lockfile` *(vercel.json theke auto)* |
| **Build Command** | `CI=false GENERATE_SOURCEMAP=false yarn build` *(vercel.json theke auto)* |
| **Output Directory** | `build` *(vercel.json theke auto)* |
| **Node.js Version** | `20.x` (Settings → General → Node.js Version) |

> Override toggle gulo **OFF** rakhben. Tahole `vercel.json`-er value-i use hobe.

`vercel.json`-e ja set kora ache:
- `CI=false`: choto warning-er jonno Vercel build fail korbe na
- `GENERATE_SOURCEMAP=false`: browser-er Sources-e asol code dekhabe na
- `rewrites`: `/download` er moto direct link refresh korleo 404 asbe na
- `/static/*` file-e long cache, tai site fast load hobe

---

## 2. Environment Variables (Vercel → Project → Settings → Environment Variables)

| Name | Value | Dorkar? |
|---|---|---|
| `REACT_APP_BACKEND_URL` | `https://bot.yourdomain.com` (apnar VPS backend URL, **`https://` soho, sheshe `/` chhara**) | ✅ Obosshoi |
| `GENERATE_SOURCEMAP` | `false` | ✅ (build command-eo ache, extra safety) |
| `REACT_APP_ENABLE_DOWNLOAD` | `false` | ⭕ Optional: `/download` page lukate chaile |

Environment: **Production, Preview, Development** tinta-tei tick din.

> ⚠️ **SOB CHEYE BOROSHO VUL — `https://` obosshoi dite hobe!**
> `REACT_APP_BACKEND_URL`-er value-te shuru-te **`https://` thakte-i hobe**. Shudhu domain (`bot.yourdomain.com`) dile browser etake **relative path** mone kore Vercel domain-er sathe jure dey, ar shob API call fail kore.
>
> | | Value | Result |
> |---|---|---|
> | ✅ Thik | `https://bot.yourdomain.com` | API call → `https://bot.yourdomain.com/api/...` |
> | ❌ Vul | `bot.yourdomain.com` (https:// nei) | API call → `https://your-site.vercel.app/bot.yourdomain.com/api/...` → **405 / undefined** |
>
> **Vul hole je somossa dekhbe:**
> - Telegram button-er link `https://t.me/undefined?start=...` (bot username `undefined`) — karon `/api/public/config` fail korche
> - DevTools → Network-e `/api/track/pageview` **405 Method Not Allowed**, ar Request URL-e vercel.app + bot domain duita jora
>
> **Fix:** value `https://bot.yourdomain.com` kore save koro → **Redeploy** (build cache off).

> Env change korle **Redeploy** korte hobe (Deployments → ⋯ → Redeploy). React-er env build-er somoy code-er bhitore boshe jay.

> `REACT_APP_BACKEND_URL` er jaygay je URL diben, shei server-e bot backend chalu thakte hobe (`/root/tg-ads-bot`, `vps-run.md` dekhun). Check: `https://bot.yourdomain.com/api/` khulle `{"message":"ok"}` asbe.

---

## 3. Deploy er step

### Option A: GitHub diye (recommended)
1. Emergent chat-er **"Save to GitHub"** diye code GitHub-e push korun
2. Vercel → **Add New → Project** → GitHub repo select korun
3. **Root Directory** → `frontend` → **Edit** e chap diye select korun
4. Step 2-er **Environment Variables** add korun
5. **Deploy** e chap din

Er por GitHub-e notun code push korlei Vercel nije-i notun deploy korbe.

### Option B: Vercel CLI diye
```bash
npm i -g vercel
cd frontend
vercel login
vercel env add REACT_APP_BACKEND_URL production   # value: https://bot.yourdomain.com
vercel --prod
```

---

## 4. Custom domain (optional)
Vercel → Project → **Settings → Domains** → domain add korun (jemon `yourdomain.com`). Vercel je DNS record dekhabe, sheta domain provider-e add korun.

> Website (`yourdomain.com`, Vercel) ar bot backend (`bot.yourdomain.com`, VPS) alada subdomain-e rakhun.

---

## 5. Deploy-er por check
- Website khulun → page load hocche kina dekhun
- **Join button** e chap din → Telegram bot khulbe (`?start=...` soho)
- Browser DevTools → Network: `/api/public/config` ar `/api/track/pageview` **200** dicche kina dekhun
- Bot admin panel → 📊 Stats → "🌐 পেজ ভিজিট" bariche kina dekhun

## Somossha holo
| Somossha | Shomadhan |
|---|---|
| Build fail: `Treating warnings as errors` | Build Command-e `CI=false` ache kina dekhun (vercel.json) |
| Join button-e Telegram khule na / API error | `REACT_APP_BACKEND_URL` thik ache kina dekhun, tarpor **Redeploy** din |
| Link `t.me/undefined?start=...` / `/api` call-e **405** / Request URL-e vercel.app + bot domain jora | `REACT_APP_BACKEND_URL`-e **`https://` missing**. Value `https://bot.yourdomain.com` kore save → **Redeploy** (build cache off) |
| `/download` ba onno link refresh korle 404 | `vercel.json` `frontend` folder-e ache kina, ar Root Directory `frontend` kina dekhun |
| CORS error | Backend `.env`-e `CORS_ORIGINS="*"` (ba `"https://yourdomain.com"`) din, tarpor `systemctl restart tg-ads-bot` |
| Purono backend URL use hocche | Env update korar por Redeploy din |
