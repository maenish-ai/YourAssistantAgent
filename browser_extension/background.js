const base = "http://127.0.0.1:8765";

async function post(path, data) {
  return fetch(base + path, {method: "POST", headers: {"Content-Type": "application/json", "X-YAA-Bridge": "1"}, body: JSON.stringify(data)});
}

async function hello() {
  try {
    const tabs = await chrome.tabs.query({});
    await post("/hello", {browser: navigator.userAgent, tabs: tabs.length});
  } catch (_) {}
}

async function activeTab() {
  const tabs = await chrome.tabs.query({active: true, currentWindow: true});
  if (!tabs.length) throw new Error("No active tab");
  return tabs[0];
}

async function inTab(tabId, func, args=[]) {
  const results = await chrome.scripting.executeScript({target: {tabId}, func, args});
  return results && results.length ? results[0].result : null;
}

async function waitForTab(tabId, timeoutMs=20000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return tab;
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error("Page did not finish loading before the timeout");
}

async function discoverFacebookGroups(limit, deep=false) {
  const tab = await chrome.tabs.create({url: "https://www.facebook.com/groups/joins/", active: false});
  try {
    await waitForTab(tab.id, deep ? 25000 : 8000);
    const result = await inTab(tab.id, async (wanted, fullScan) => {
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      const blocked = () => {
        const u = String(location.href || "").toLowerCase();
        return u.includes("/login") || u.includes("/checkpoint") ||
          !!document.querySelector("input[name='email'],input[name='pass']");
      };
      if (blocked()) return {ok:false, error:"facebook_login_required", groups:[], url:location.href};

      const reserved = new Set(["feed","discover","create","joins","for_you","notifications","gaming","category","search","membership","requests"]);
      const found = new Map();
      const scan = () => {
        for (const a of document.querySelectorAll("a[href*='/groups/']")) {
          let u;
          try { u = new URL(a.href || a.getAttribute("href") || "", location.href); }
          catch (_) { continue; }
          if (!/(^|\.)facebook\.com$/i.test(u.hostname)) continue;
          const parts = u.pathname.split("/").filter(Boolean);
          if (parts.length < 2 || parts[0].toLowerCase() !== "groups") continue;
          const slug = String(parts[1] || "").trim();
          if (!slug || reserved.has(slug.toLowerCase())) continue;
          const raw = String(a.innerText || a.textContent || a.getAttribute("aria-label") || a.getAttribute("title") || "").trim();
          const name = raw.split(/\r?\n/).map(x => x.replace(/\s+/g," ").trim()).find(Boolean) || "";
          if (!name) continue;
          const url = `https://www.facebook.com/groups/${slug}`;
          if (!found.has(url)) found.set(url, {name:name.slice(0,180), url});
          if (found.size >= wanted) return true;
        }
        return false;
      };

      let stagnant = 0;
      let previous = 0;
      for (let round=0; round<(fullScan ? 24 : 5); round++) {
        if (scan()) break;
        if (found.size === previous) stagnant++; else stagnant = 0;
        previous = found.size;
        if (stagnant >= (fullScan ? 4 : 2)) break;
        window.scrollBy(0, Math.max(1500, Math.floor(window.innerHeight * 1.8)));
        await sleep(fullScan ? 900 : 350);
        if (blocked()) return {ok:false, error:"facebook_checkpoint_or_login", groups:[...found.values()], url:location.href};
      }
      scan();
      return {ok:true, groups:[...found.values()].slice(0,wanted), url:location.href};
    }, [Math.max(1, Math.min(1000, Number(limit || 500))), deep]);
    return result || {ok:false, error:"empty_discovery_result", groups:[]};
  } finally {
    try { await chrome.tabs.remove(tab.id); } catch (_) {}
  }
}

async function facebookSession() {
  const tab = await chrome.tabs.create({url: "https://www.facebook.com/me", active: false});
  try {
    await waitForTab(tab.id, 8000);
    const result = await inTab(tab.id, async () => {
      const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
      for (let attempt = 0; attempt < 8; attempt++) {
        const url = new URL(location.href);
        const path = url.pathname.toLowerCase();
        if (!/(^|\.)facebook\.com$/i.test(url.hostname)) {
          return {ok: false, status: "unknown", error: "unexpected_facebook_redirect"};
        }
        if (/^\/(checkpoint|two_step_verification)(?:\/|$)/.test(path)) {
          return {ok: true, status: "checkpoint", url: location.href};
        }
        if (/^\/(login|recover|reg)(?:\/|\.|$)/.test(path) ||
            document.querySelector("input[name='email'],input[name='pass']")) {
          return {ok: true, status: "not_connected", url: location.href};
        }
        const account = document.querySelector(
          '[role="button"][aria-label="Account"], [role="button"][aria-label="Your profile"], ' +
          '[role="button"][aria-label="حسابك"], [role="button"][aria-label="ملفك الشخصي"]');
        // A profile URL can be public. Only rendered account controls provide
        // positive evidence that this browser has an authenticated session.
        if (account) {
          return {ok: true, status: "connected", url: location.href};
        }
        if (attempt < 7) await sleep(250);
      }
      return {ok: false, status: "unknown", error: "facebook_session_unverified", url: location.href};
    });
    return result || {ok: false, status: "unknown", error: "empty_session_result"};
  } finally {
    try { await chrome.tabs.remove(tab.id); } catch (_) {}
  }
}

async function facebookPageResults(name, expiresAt) {
  const tab = await activeTab();
  const query = String(name || "").trim();
  if (!query || query.length > 180) return {ok:false, error:"invalid_page_name"};
  const search = new URL("https://www.facebook.com/search/pages/");
  search.searchParams.set("q", query);
  await chrome.tabs.update(tab.id, {url: search.href});
  const deadline = Math.min(Date.now() + 12000, expiresAt ? expiresAt * 1000 : Infinity);
  let previousMatches = "";
  while (Date.now() < deadline) {
    const current = await chrome.tabs.get(tab.id);
    if (current.status === "complete") {
      const inspected = await inTab(tab.id, (query, expectedQuery) => {
        const url = new URL(location.href);
        if (url.hostname !== "www.facebook.com") return {blocked:true};
        if (url.pathname.startsWith("/login") || url.pathname.startsWith("/checkpoint")) return {blocked:true};
        if (url.pathname.replace(/\/$/, "") !== "/search/pages"
            || url.searchParams.get("q") !== expectedQuery) return {moved:true};
        const normalize = value => value.normalize("NFKC").toLowerCase()
          .replace(/[أإآٱ]/g, "ا").replace(/[\u064b-\u065f\u0670\u0640]/g, "").replace(/\s+/g, " ").trim();
        const matches = new Map();
        for (const link of document.querySelectorAll("main a[href], [role=main] a[href]")) {
          const name = (link.innerText || link.getAttribute("aria-label") || "").trim();
          if (!name || normalize(name) !== normalize(query) || !link.getClientRects().length) continue;
          const href = new URL(link.href);
          if (href.origin !== url.origin || !/^\/[a-z0-9._-]+\/?$/i.test(href.pathname)) continue;
          if (/^\/(?:profile\.php|search|login|checkpoint|groups|pages|watch|events|marketplace|reel|gaming|help|share|photo|feed)\/?$/i.test(href.pathname)) continue;
          const canonical = href.origin + href.pathname.replace(/\/$/, "");
          matches.set(canonical, {name, url:canonical});
          if (matches.size > 5) break;
        }
        return {matches:[...matches.values()]};
      }, [query, query]);
      if (inspected?.blocked || inspected?.moved) return {ok:false, error:"search_not_available"};
      if (inspected?.matches?.length) {
        const key = JSON.stringify(inspected.matches);
        if (key === previousMatches) return {ok:true, tabId:tab.id, query, matches:inspected.matches};
        previousMatches = key;
      } else {
        previousMatches = "";
      }
    }
    await new Promise(resolve => setTimeout(resolve, 600));
  }
  return {ok:true, matches:[]};
}

async function openFacebookPageResult(args) {
  const tab = await activeTab();
  if (tab.id !== args.tabId) return {ok:false, error:"active_tab_changed"};
  const target = new URL(args.url);
  if (target.origin !== "https://www.facebook.com") return {ok:false, error:"invalid_result"};
  const visible = await inTab(tab.id, (url, query, name) => {
    const current = new URL(location.href);
    if (current.origin !== "https://www.facebook.com" || current.pathname.replace(/\/$/, "") !== "/search/pages"
        || current.searchParams.get("q") !== query) return false;
    return [...document.querySelectorAll("main a[href], [role=main] a[href]")].some(link => {
      const href = new URL(link.href);
      return href.origin + href.pathname.replace(/\/$/, "") === url
          && (link.innerText || link.getAttribute("aria-label") || "").trim() === name
          && link.getClientRects().length;
    });
  }, [target.href, args.query, args.name]);
  if (!visible) return {ok:false, error:"result_not_visible"};
  await chrome.tabs.update(tab.id, {url:target.href});
  const loaded = await waitForTab(tab.id, 10000);
  const actual = new URL(loaded.url);
  const confirmed = actual.origin === target.origin && actual.pathname.replace(/\/$/, "") === target.pathname.replace(/\/$/, "");
  return {ok:confirmed, url:confirmed ? actual.origin + actual.pathname : ""};
}

async function execute(command) {
  const a = command.action;
  const x = command.arguments || {};
  if (a === "facebook_page_results") return facebookPageResults(x.name, command.expires_at);
  if (a === "open_facebook_page_result") return openFacebookPageResult(x);
  if (a === "open_url") {
    const tab = await chrome.tabs.create({url: String(x.url || ""), active: x.active !== false});
    return {ok: true, tabId: tab.id, url: tab.url || String(x.url || "")};
  }
  if (a === "probe_url") {
    const r = await fetch(String(x.url || ""), {credentials: "include", redirect: "follow"});
    const text = await r.text();
    return {ok: r.ok, status: r.status, url: r.url, text: text.slice(0, Number(x.max_chars || 5000))};
  }
  if (a === "facebook_session") {
    return facebookSession();
  }
  if (a === "discover_facebook_groups") {
    return discoverFacebookGroups(x.limit, x.deep === true);
  }
  const tab = await activeTab();
  if (a === "active_page") {
    const info = await inTab(tab.id, () => ({url: location.href, title: document.title, text: (document.body?.innerText || "").slice(0, 5000)}));
    return {ok: true, tabId: tab.id, ...info};
  }
  if (a === "extract_links") {
    const result = await inTab(tab.id, (needle, limit) => {
      const out=[]; const n=String(needle||"").toLowerCase();
      for (const el of document.querySelectorAll("a[href]")) {
        const href=el.href||""; const text=(el.innerText||el.textContent||"").trim();
        if (!n || href.toLowerCase().includes(n) || text.toLowerCase().includes(n)) out.push({text,href});
        if (out.length>=limit) break;
      }
      return out;
    }, [String(x.contains || ""), Math.min(1000, Number(x.limit || 200))]);
    return {ok: true, links: result || []};
  }
  if (a === "click_selector") {
    const ok = await inTab(tab.id, (selector) => { const el=document.querySelector(selector); if(!el)return false; el.click(); return true; }, [String(x.selector||"")]);
    return {ok: !!ok};
  }
  if (a === "click_text") {
    const ok = await inTab(tab.id, (needle) => {
      const n=String(needle||"").trim().toLowerCase();
      const els=[...document.querySelectorAll("button,a,[role=button]")];
      const el=els.find(e => (e.innerText||e.textContent||"").trim().toLowerCase().includes(n));
      if(!el)return false; el.click(); return true;
    }, [String(x.text||"")]);
    return {ok: !!ok};
  }
  if (a === "type_selector") {
    const ok = await inTab(tab.id, (selector, value) => {
      const el=document.querySelector(selector); if(!el)return false; el.focus();
      const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value")?.set;
      if(setter)setter.call(el,String(value)); else el.value=String(value);
      el.dispatchEvent(new Event("input",{bubbles:true})); el.dispatchEvent(new Event("change",{bubbles:true})); return true;
    }, [String(x.selector||""), String(x.value||"")]);
    return {ok: !!ok};
  }
  throw new Error("Unsupported action");
}

// One command at a time: overlapping intervals must never drive different pages
// concurrently while a previous discovery or click is still running.
let polling = false;
let pendingResult = null;

async function poll() {
  if (polling) return;
  polling = true;
  try {
    // Keep a completed result until the app acknowledges it. A transient bridge
    // failure must not lose the result or cause the command to run twice.
    if (pendingResult) {
      const ack = await post("/command-result", pendingResult);
      if (!ack.ok) return;
      pendingResult = null;
    }
    const r = await fetch(base + "/next-command", {headers: {"X-YAA-Bridge": "1"}});
    if (!r.ok) return;
    const data = await r.json();
    if (data.command) {
      let result;
      try {
        if (data.command.expires_at && Date.now() >= data.command.expires_at * 1000) {
          result = {ok: false, error: "command_expired"};
        } else {
          result = await execute(data.command);
        }
      }
      catch (e) { result = {ok: false, error: String(e && e.message || e)}; }
      pendingResult = {id: data.command.id, result};
      const ack = await post("/command-result", pendingResult);
      if (ack.ok) pendingResult = null;
    }
  } catch (_) {
    // The desktop app can be closed; the next wakeup will reconnect.
  } finally {
    polling = false;
  }
}

const WAKE_ALARM = "yaa-browser-bridge";
async function wakeBridge() {
  try {
    // Unlike setInterval, alarms survive Manifest V3 worker suspension. Chrome
    // 120+ supports 30-second alarms; older browsers may clamp this to a minute.
    await chrome.alarms.create(WAKE_ALARM, {periodInMinutes: 0.5});
  } catch (_) {}
  await hello();
  await poll();
}

// Register listeners synchronously, before any asynchronous startup work.
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === WAKE_ALARM) {
    void hello();
    void poll();
  }
});
chrome.runtime.onStartup.addListener(() => { void wakeBridge(); });
chrome.runtime.onInstalled.addListener(() => { void wakeBridge(); });
chrome.action.onClicked.addListener(() => { void wakeBridge(); });

void wakeBridge();
setInterval(hello, 3000);
setInterval(poll, 650);
