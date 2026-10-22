# /download bondho / remove korar niyom

`/download` page theke jekeu puro source code zip download korte pare. Eta 2 bhabe bondho kora jay.

---

## Option 1: Shudhu `.env` edit (shobcheye shohoj, abar chalu kora jay)

### Backend (download API bondho)
`backend/.env`-e ei line add korun:
```
ENABLE_DOWNLOAD="false"
```
Tarpor backend restart:
- VPS: `systemctl restart tg-ads-bot`
- Emergent: chat-e bolun "backend restart koro"

Ekhon `/api/download/source` **404** dibe, kono zip download hobe na.

### Frontend (download page lukano)
`frontend/.env`-e ei line add korun:
```
REACT_APP_ENABLE_DOWNLOAD=false
```
- Emergent preview: frontend restart lagbe (`sudo supervisorctl restart frontend`)
- VPS / production: abar build din: `cd /root/tg-ads-bot/frontend && yarn build`

Ekhon `/download` link khulle normal landing page dekhabe.

> **Abar chalu korte:** duita line muche din (ba `"true"` kore din), tarpor restart/build din.

> Shudhu backend bondho korlei code download puro bondho. Frontend line ta shudhu page ta lukay.

---

## Option 2: Puro file muche fela (permanent)

1. **`backend/server.py`** theke ei line gulo muche din:
   ```python
   from download import router as download_router  # noqa: E402
   ```
   ```python
   if os.environ.get("ENABLE_DOWNLOAD") != "false":
       api_router.include_router(download_router)
   ```
2. **`backend/download.py`** file ta delete korun.
3. **`frontend/src/App.js`** theke ei line gulo muche din:
   ```js
   import DownloadPage from "@/pages/DownloadPage";
   ```
   ```jsx
   {process.env.REACT_APP_ENABLE_DOWNLOAD !== "false" && (
     <Route path="/download" element={<DownloadPage />} />
   )}
   ```
4. **`frontend/src/pages/DownloadPage.jsx`** file ta delete korun.
5. Backend restart ar frontend restart/build din (Option 1-er moto).

---

## Check
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://YOUR_DOMAIN/api/download/source
```
`404` dekhale download bondho hoye geche.
