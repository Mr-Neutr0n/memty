// Memty Bridge content script: a floating [⚡ Memty] pill on the prompt box.
// ⚡ Memty / Alt+M  -> prepend your local capsule to the prompt (visible, editable).
// + Save Facts      -> extract facts from the latest answer locally, review, then save.
// Network calls go through background.js; this script never sees the pairing token.
(() => {
  if (window.__memtyBridge) return;
  window.__memtyBridge = true;

  const EDITORS = [
    "#prompt-textarea",                       // ChatGPT
    'div.ProseMirror[contenteditable="true"]', // Claude.ai, ChatGPT
    "rich-textarea .ql-editor",                // Gemini
    'textarea[placeholder]',                   // Perplexity
    'div[contenteditable="true"][role="textbox"]',
    "textarea",
  ];
  // Best-effort answer selectors; a text selection always takes priority.
  const ANSWERS = {
    "chatgpt.com": '[data-message-author-role="assistant"]',
    "chat.openai.com": '[data-message-author-role="assistant"]',
    "claude.ai": '[data-testid="assistant-message"], .font-claude-response, .font-claude-message',
    "gemini.google.com": "model-response, message-content",
    "www.perplexity.ai": ".prose",
    "perplexity.ai": ".prose",
  };
  const MARKER = "<memty_state";

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;z-index:2147483647;display:none;";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
    <style>
      :host { all: initial; }
      .bar { display:flex; gap:6px; font:600 12px/1 system-ui,sans-serif; }
      button { all:unset; cursor:pointer; padding:6px 10px; border-radius:999px;
               background:#111827; color:#fff; box-shadow:0 1px 4px rgba(0,0,0,.25); }
      button:hover { background:#374151; }
      .panel { position:absolute; bottom:34px; right:0; width:340px; max-height:320px; overflow:auto;
               background:#fff; color:#111; border:1px solid #d1d5db; border-radius:10px; padding:10px;
               font:13px/1.4 system-ui,sans-serif; box-shadow:0 6px 24px rgba(0,0,0,.2); }
      .panel label { display:flex; gap:6px; margin:4px 0; align-items:flex-start; }
      .panel .row { display:flex; gap:6px; justify-content:flex-end; margin-top:8px; }
      .panel .row button { padding:5px 10px; }
      .toast { position:absolute; bottom:34px; right:0; white-space:nowrap; background:#111827; color:#fff;
               padding:6px 10px; border-radius:8px; font:12px system-ui,sans-serif; }
      [hidden] { display:none !important; }
    </style>
    <div class="panel" hidden></div>
    <div class="toast" hidden></div>
    <div class="bar">
      <button class="inject" title="Add your Memty capsule (Alt+M)">⚡ Memty</button>
      <button class="save" title="Extract facts from the latest answer">+ Save Facts</button>
    </div>`;
  const panel = root.querySelector(".panel");
  const toastEl = root.querySelector(".toast");
  document.documentElement.appendChild(host);

  let editor = null;
  let toastTimer = 0;

  const visible = (el) => !!el && el.isConnected && el.getClientRects().length > 0;
  const isEditor = (el) => !!el && (el.tagName === "TEXTAREA" || el.isContentEditable);

  function findEditor() {
    const active = document.activeElement;
    if (isEditor(active) && !host.contains(active)) return active.closest('[contenteditable="true"]') || active;
    if (visible(editor)) return editor;
    for (const selector of EDITORS) {
      const found = [...document.querySelectorAll(selector)].find(visible);
      if (found) return found;
    }
    return null;
  }

  function place() {
    editor = findEditor();
    if (!editor) { host.style.display = "none"; return; }
    const rect = editor.getBoundingClientRect();
    host.style.display = "block";
    host.style.top = `${Math.max(4, rect.top - 34)}px`;
    host.style.left = `${Math.max(4, rect.right - 200)}px`;
  }

  function toast(text) {
    toastEl.textContent = text;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 4000);
  }

  function ask(message) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(message, (reply) => {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        reply?.ok ? resolve(reply.result) : reject(new Error(reply?.error || "No response from Memty"));
      });
    });
  }

  function textOf(el) {
    return el.tagName === "TEXTAREA" ? el.value : el.innerText;
  }

  function prepend(el, text) {
    el.focus();
    if (el.tagName === "TEXTAREA") {
      // Use the native setter so React-controlled textareas register the change.
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
      setter.call(el, `${text}\n\n${el.value}`);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.setSelectionRange(el.value.length, el.value.length);
      return;
    }
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(true);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    // insertText goes through the editor's own input pipeline (ProseMirror, Quill, Lexical).
    if (!document.execCommand("insertText", false, `${text}\n\n`)) {
      el.prepend(document.createTextNode(`${text}\n\n`));
      el.dispatchEvent(new InputEvent("input", { bubbles: true }));
    }
  }

  async function inject() {
    const el = findEditor();
    if (!el) return toast("Click into the prompt box first.");
    if (textOf(el).includes(MARKER)) return toast("Memty capsule is already in this prompt.");
    try {
      const capsule = await ask({ type: "capsule" });
      if (!capsule.text) return toast(`No facts in ${capsule.namespace} yet.`);
      prepend(el, capsule.text);
      const note = capsule.redacted ? `, ${capsule.redacted} redacted` : "";
      toast(`Added ${capsule.namespace} (~${capsule.approx_tokens} tokens${note}).`);
    } catch (error) {
      toast(error.message);
    }
  }

  function latestAnswer() {
    const selected = String(window.getSelection() || "").trim();
    if (selected) return selected;
    const selector = ANSWERS[location.hostname];
    const nodes = selector ? [...document.querySelectorAll(selector)].filter(visible) : [];
    if (!nodes.length) return "";
    const answer = nodes[nodes.length - 1];
    // Code samples are not facts: drop rendered code blocks before extracting.
    let text = answer.innerText;
    for (const block of answer.querySelectorAll("pre, code-block")) {
      if (block.innerText.trim()) text = text.replace(block.innerText, "\n");
    }
    return text.trim();
  }

  function review(facts) {
    panel.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = "Save these facts to Memty?";
    panel.append(title);
    const boxes = facts.map((fact) => {
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = true;
      const text = document.createElement("span");
      text.textContent = `${fact.slot}: ${fact.value}`; // textContent: never render page HTML
      label.append(box, text);
      panel.append(label);
      return { box, fact };
    });
    const row = document.createElement("div");
    row.className = "row";
    const cancel = Object.assign(document.createElement("button"), { textContent: "Cancel" });
    const save = Object.assign(document.createElement("button"), { textContent: "Save" });
    row.append(cancel, save);
    panel.append(row);
    panel.hidden = false;
    cancel.onclick = () => { panel.hidden = true; };
    save.onclick = async () => {
      const chosen = boxes.filter((b) => b.box.checked).map((b) => b.fact);
      panel.hidden = true;
      if (!chosen.length) return toast("Nothing selected.");
      try {
        const result = await ask({ type: "save", facts: chosen });
        const skipped = result.skipped.length ? `, ${result.skipped.length} kept as-is` : "";
        toast(`Saved ${result.saved.length} fact(s) to ${result.namespace}${skipped}.`);
      } catch (error) {
        toast(error.message);
      }
    };
  }

  async function saveFacts() {
    const text = latestAnswer();
    if (!text) return toast("Select the answer text, then click Save Facts.");
    try {
      const { facts } = await ask({ type: "extract", text: text.slice(0, 50000) });
      facts.length ? review(facts) : toast("No facts found in that answer.");
    } catch (error) {
      toast(error.message);
    }
  }

  // Keep focus in the prompt box when the pill is clicked.
  root.querySelector(".bar").addEventListener("mousedown", (event) => event.preventDefault());
  root.querySelector(".inject").addEventListener("click", inject);
  root.querySelector(".save").addEventListener("click", saveFacts);
  document.addEventListener("keydown", (event) => {
    if (event.altKey && !event.ctrlKey && !event.metaKey && event.code === "KeyM") {
      event.preventDefault();
      event.stopPropagation();
      inject();
    }
  }, true);

  let frame = 0;
  const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; place(); }); };
  ["focusin", "resize", "scroll"].forEach((name) => window.addEventListener(name, schedule, true));
  setInterval(schedule, 1500); // single-page apps swap the prompt box without events
  place();
})();
