import { PASSWORD_HASH } from "./config.js";

const STORAGE_KEY = "busy-day:auth";

async function sha256Hex(s) {
  const buf = new TextEncoder().encode(s);
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function isAuthed() {
  if (!PASSWORD_HASH) return true;
  return sessionStorage.getItem(STORAGE_KEY) === PASSWORD_HASH;
}

export async function tryUnlock(input) {
  if (!PASSWORD_HASH) return true;
  const h = await sha256Hex(input);
  if (h === PASSWORD_HASH) {
    sessionStorage.setItem(STORAGE_KEY, h);
    return true;
  }
  return false;
}

export function bindGate({ gateEl, formEl, inputEl, errorEl, onPass }) {
  if (isAuthed()) {
    onPass();
    return;
  }
  gateEl.hidden = false;
  document.body.dataset.state = "gate";
  formEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.hidden = true;
    const ok = await tryUnlock(inputEl.value);
    if (!ok) {
      errorEl.hidden = false;
      inputEl.select();
      return;
    }
    gateEl.hidden = true;
    onPass();
  });
}
