import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
let pageviewSent = false;
let botUsername = null;

const uuid = () =>
  window.crypto?.randomUUID
    ? window.crypto.randomUUID()
    : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
      });

const getCookie = (name) => {
  const row = document.cookie.split("; ").find((x) => x.startsWith(`${name}=`));
  return row ? decodeURIComponent(row.split("=").slice(1).join("=")) : null;
};

const setCookie = (name, value, days) => {
  const exp = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${exp}; path=/; SameSite=Lax`;
};

const getVisitorId = () => {
  let id = localStorage.getItem("vid");
  if (!id) {
    id = uuid();
    localStorage.setItem("vid", id);
  }
  return id;
};

const ensureMetaCookies = () => {
  const now = Date.now();
  const fbclid = new URLSearchParams(window.location.search).get("fbclid");
  const fbc = getCookie("_fbc");
  if (fbclid && (!fbc || !fbc.endsWith(`.${fbclid}`))) setCookie("_fbc", `fb.1.${now}.${fbclid}`, 90);
  if (!getCookie("_fbp")) setCookie("_fbp", `fb.1.${now}.${Math.floor(Math.random() * 1e10)}`, 90);
  return { fbp: getCookie("_fbp"), fbc: getCookie("_fbc") };
};

const loadPixel = (pixelId, visitorId, eventId) => {
  if (!window.fbq) {
    const f = function (...args) {
      f.callMethod ? f.callMethod(...args) : f.queue.push(args);
    };
    f.push = f;
    f.queue = [];
    f.loaded = true;
    f.version = "2.0";
    window.fbq = f;
    window._fbq = f;
    const s = document.createElement("script");
    s.async = true;
    s.src = "https://connect.facebook.net/en_US/fbevents.js";
    document.head.appendChild(s);
  }
  window.fbq("init", pixelId, { external_id: visitorId });
  window.fbq("track", "PageView", {}, { eventID: eventId });
};

const basePayload = () => ({ visitor_id: getVisitorId(), url: window.location.href, ...ensureMetaCookies() });

export async function trackPageView() {
  if (pageviewSent) return;
  pageviewSent = true;
  const { data: cfg } = await axios.get(`${API}/public/config`);
  botUsername = cfg.bot_username;
  localStorage.setItem("bot_username", botUsername);
  const eventId = uuid();
  const payload = { ...basePayload(), event_id: eventId, referrer: document.referrer || null };
  if (cfg.pixel_id) loadPixel(cfg.pixel_id, payload.visitor_id, eventId);
  await axios.post(`${API}/track/pageview`, payload);
}

export function getInstantLink() {
  const bot = botUsername || localStorage.getItem("bot_username");
  if (!bot) return null;
  const token = uuid().replace(/-/g, "");
  fetch(`${API}/track/start-link`, {
    method: "POST",
    keepalive: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...basePayload(), token }),
  }).catch(() => {});
  return `https://t.me/${bot}?start=${token}`;
}

export async function getDeepLink() {
  const instant = getInstantLink();
  if (instant) return instant;
  try {
    const { data } = await axios.post(`${API}/track/start-link`, basePayload(), { timeout: 6000 });
    return data.deep_link;
  } catch (e) {
    return botUsername ? `https://t.me/${botUsername}` : null;
  }
}
