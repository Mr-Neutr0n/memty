const $ = (id) => document.getElementById(id);
const status = (text) => { $("status").textContent = text; };

chrome.storage.local.get({ port: 8765, token: "", namespace: "" }).then((saved) => {
  $("port").value = saved.port;
  $("token").value = saved.token;
  $("namespace").value = saved.namespace;
});

$("save").addEventListener("click", async () => {
  const port = Number($("port").value) || 8765;
  const token = $("token").value.trim();
  const namespace = $("namespace").value.trim().toLowerCase();
  await chrome.storage.local.set({ port, token, namespace });
  try {
    const response = await fetch(`http://127.0.0.1:${port}/namespaces`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return status(`Saved, but Memty refused: ${body.message || response.status}`);
    const list = $("namespaces");
    list.replaceChildren(...body.namespaces.map((name) => Object.assign(document.createElement("option"), { value: name })));
    const known = body.namespaces.includes(namespace);
    status(`Connected. ${body.namespaces.length} namespace(s) in your vault.` +
      (namespace && !known ? `\n"${namespace}" has no facts yet; Save Facts will create it.` : ""));
  } catch {
    status("Saved, but Memty is not running. Start it with: memty serve --background");
  }
});
