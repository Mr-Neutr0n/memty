import { getAllModels } from '/static/registry.js';

/* ── Auth guard ── */
const userRaw = localStorage.getItem('nexoraiUser');
if (!userRaw) { window.location.href = '/login'; }
let userName = 'User';
try {
    const u = JSON.parse(userRaw);
    userName = u.name || u.email || 'User';
    document.getElementById('userNameEl').textContent = userName;
    document.getElementById('avatarEl').textContent = userName[0].toUpperCase();
} catch(e) {}

window.logout = () => { localStorage.removeItem('nexoraiUser'); fetch('/users/logout', { method: 'POST' }).finally(() => { window.location.href = '/login'; }); };
window.toggleSidebar = (open) => {
    document.querySelector('.sidebar').classList.toggle('open', open);
    document.getElementById('sidebarBackdrop').classList.toggle('open', open);
};

/* ── Theme ── */
let isLight = localStorage.getItem('nexorTheme') === 'light';
if (isLight) applyTheme(true);
window.toggleTheme = () => { isLight = !isLight; applyTheme(isLight); localStorage.setItem('nexorTheme', isLight ? 'light' : 'dark'); };
function applyTheme(light) {
    document.querySelector('.legacy-page-chat')?.classList.toggle('light', light);
    document.getElementById('themeLabel').textContent = light ? 'Dark Mode' : 'Light Mode';
}

/* ── Models ── */
const MODELS = getAllModels();
const MODEL_LOGOS = {
    'gemini-flash':  { src: '/static/assets/gemini.png',  invert: false, className: 'gemini-logo' },
    'grok-ai':       { src: '/static/assets/groak.webp',  invert: false, className: 'grok-logo' },
    'claude-haiku':   { src: '/static/assets/claude.png',  invert: false },
    'nemotron':      { src: '/static/assets/nvdia.jpg',   invert: false, className: 'nvidia-logo' },
    'chatgpt':       { src: '/static/assets/openai.jpg',   invert: false, className: 'openai-logo' },
    'kimi':          { src: '',                            invert: false },
    'llama':         { src: '/static/assets/meta.png',    invert: false, className: 'meta-logo' }
};

let currentModel = MODELS[0];

// Build model grid
const grid = document.getElementById('modelsGrid');
MODELS.forEach(m => {
    const lp = MODEL_LOGOS[m.id];
    const card = document.createElement('div');
    card.className = `model-card ${m.id === currentModel.id ? 'selected' : ''}`;
    card.dataset.id = m.id;
    card.innerHTML = `
        <div class="mc-head">
            <div class="mc-logo ${lp?.className || ''} ${m.id === 'gemini-flash' ? 'dark-bg' : ''}" style="background:${m.available ? 'rgba(16,163,127,0.12)' : 'rgba(255,255,255,0.05)'};">
                ${lp?.src ? `<img src="${lp.src}" alt="${m.displayName}" style="${lp.invert && !isLight ? 'filter:invert(1) brightness(2);' : ''}">` : `<span style="font-size:20px;">🌙</span>`}
            </div>
            <div>
                <div class="mc-name">${m.displayName}</div>
                <div class="mc-provider">${m.provider}</div>
            </div>
        </div>
        <div class="mc-desc">${m.description}</div>
        <span class="mc-badge ${m.proOnly ? 'pro' : m.available ? 'avail' : 'soon'}">${m.proOnly ? '◆ Pro plan' : m.available ? '● Available' : '◌ Coming Soon'}</span>
    `;
    card.onclick = () => selectModel(m);
    grid.appendChild(card);
});

fetch('/api/config', { cache: 'no-store' }).then(response => response.json()).then(config => {
    for (const serverModel of config.models || []) {
        const model = MODELS.find(item => item.id === serverModel.id);
        if (!model || model.id === 'auto') continue;
        model.available = serverModel.available;
        const card = grid.querySelector(`[data-id="${model.id}"]`);
        const badge = card?.querySelector('.mc-badge');
        if (badge) {
            badge.className = `mc-badge ${model.available ? 'avail' : 'soon'}`;
            badge.textContent = model.available ? '● Configured' : '○ Add provider key';
        }
        const details = document.createElement('div');
        details.className = 'mc-runtime';
        const price = serverModel.rates ? ` · $${serverModel.rates.inputUsdPerMillion}/$${serverModel.rates.outputUsdPerMillion} per 1M in/out` : ` · ${serverModel.costTier} cost`;
        details.textContent = `${Math.round(serverModel.contextWindow / 1000)}k context · ${serverModel.speedTier}${price} · ${serverModel.vision ? 'vision' : 'text'}`;
        card?.querySelector('.mc-desc')?.after(details);
        const option = compareModelSelect.querySelector(`option[value="${model.id}"]`);
        if (option) option.disabled = !model.available;
    }
}).catch(() => {});

const compareModelSelect = document.createElement('select');
compareModelSelect.className = 'composer-compare';
compareModelSelect.setAttribute('aria-label', 'Compare response with another model');
compareModelSelect.title = 'Optional: compare each answer with a second model';
compareModelSelect.innerHTML = '<option value="">Compare off</option>' + MODELS.filter(model => model.id !== 'auto').map(model => `<option value="${model.id}">${model.displayName}</option>`).join('');
document.getElementById('composerModel')?.after(compareModelSelect);
const memoryLink = document.createElement('a');
memoryLink.className = 'sidebar-btn memory-center-link';
memoryLink.href = '/memory';
memoryLink.textContent = 'Portable memory';
document.querySelector('.sidebar-footer')?.prepend(memoryLink);

window.openModels = () => document.getElementById('modelModal').classList.add('open');
window.closeModels = () => document.getElementById('modelModal').classList.remove('open');
window.closeLock = () => document.getElementById('lockModal').classList.remove('open');
window.openProPlan = () => {
    document.getElementById('lockTitle').textContent = 'NexorAI Pro';
    document.getElementById('lockDesc').textContent = 'Pro is designed for heavier workflows with more memory, more tokens, and higher chat capacity. Connect a payment provider to enable checkout.';
    closeModels();
    document.getElementById('lockModal').classList.add('open');
};

window.selectModel = (m) => {
    if (!m.available) {
        document.getElementById('lockTitle').textContent = `${m.displayName} — Coming Soon`;
        document.getElementById('lockDesc').textContent = m.proOnly
            ? `${m.displayName} is included with NexorAI Pro. Upgrade to unlock more memory, tokens, and chat capacity.`
            : `${m.displayName} by ${m.provider} is coming soon to NexorAI.`;
        document.getElementById('lockModal').classList.add('open');
        return;
    }
    currentModel = m;
    const lp = MODEL_LOGOS[m.id];
    document.getElementById('composerModelName').textContent = m.displayName;
    const logoEl = document.getElementById('composerModelLogo');
    logoEl.alt = m.displayName;
    logoEl.src = lp?.src || '';
    logoEl.classList.toggle('invert', !!lp?.invert);
    logoEl.classList.toggle('gemini-logo', lp?.className === 'gemini-logo');
    logoEl.classList.toggle('nvidia-logo', lp?.className === 'nvidia-logo');
    logoEl.classList.toggle('meta-logo', lp?.className === 'meta-logo');
    logoEl.classList.toggle('grok-logo', lp?.className === 'grok-logo');
    logoEl.classList.toggle('openai-logo', lp?.className === 'openai-logo');

    // Update selection
    document.querySelectorAll('.model-card').forEach(c => c.classList.toggle('selected', c.dataset.id === m.id));
    closeModels();
};

/* ── History ── */
let history = [];
try { history = JSON.parse(localStorage.getItem('nexorHistory') || '[]'); } catch(e) {}
let savedConversations = [];
const activeConversationStorageKey = 'nexorActiveConversationId';

function renderHistory() {
    const list = document.getElementById('historyList');
    list.innerHTML = '';
    const byId = new Map();
    for (const item of history) {
        const key = item.conversationId || `legacy-${history.indexOf(item)}`;
        if (!byId.has(key)) byId.set(key, item);
    }
    const localConversations = [...byId.values()].map(item => ({ conversationId: item.conversationId, title: item.title || item.user || '[Attachment]' }));
    const conversations = savedConversations.length ? savedConversations : localConversations;
    const recent = conversations.slice(0, 100);
    if (!recent.length) {
        list.innerHTML = '<div class="hist-item" style="cursor:default; padding:10px;">No chats yet</div>';
        return;
    }
    recent.forEach(item => {
        const el = document.createElement('div');
        el.className = 'hist-item';
        const title = document.createElement('span');
        title.className = 'hist-title';
        title.textContent = (item.title || item.user || '[Attachment]').slice(0, 50);
        const deleteButton = document.createElement('button');
        deleteButton.className = 'hist-delete';
        deleteButton.type = 'button';
        deleteButton.title = 'Delete chat';
        deleteButton.setAttribute('aria-label', 'Delete chat');
        deleteButton.textContent = '×';
        deleteButton.onclick = event => {
            event.stopPropagation();
            const conversationId = item.conversationId;
            if (conversationId) {
                history = history.filter(entry => entry.conversationId !== conversationId);
                fetch(`/backend/memory/conversation/${encodeURIComponent(conversationId)}`, { method: 'DELETE' }).catch(() => {});
                savedConversations = savedConversations.filter(entry => entry.conversationId !== conversationId);
            }
            localStorage.setItem('nexorHistory', JSON.stringify(history));
            renderHistory();
        };
        el.onclick = () => openHistoryItem(item);
        el.append(title, deleteButton);
        list.appendChild(el);
    });
}
renderHistory();

async function refreshSavedConversations() {
    try {
        const response = await fetch('/backend/memory/conversations', { cache: 'no-store' });
        if (!response.ok) return;
        const result = await response.json();
        if (Array.isArray(result?.data?.conversations)) {
            savedConversations = result.data.conversations;
            renderHistory();
            if (savedConversations.some(item => item.conversationId === activeConversationId)) {
                openHistoryItem(savedConversations.find(item => item.conversationId === activeConversationId));
            }
        }
    } catch {}
}
void refreshSavedConversations();

// Local-first data controls: history lives in this browser profile.
const dataControls = document.createElement('div');
dataControls.className = 'local-data-controls';
dataControls.innerHTML = '<button class="sidebar-btn" type="button">Export chat history</button><button class="sidebar-btn" type="button">Delete all local chats</button>';
const [exportChatsButton, deleteChatsButton] = dataControls.querySelectorAll('button');
exportChatsButton.onclick = () => {
    const file = new Blob([JSON.stringify({ exportedAt: new Date().toISOString(), conversations: history }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(file);
    const link = document.createElement('a');
    link.href = url;
    link.download = `nexorai-chats-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
};
deleteChatsButton.onclick = () => {
    if (!history.length && !savedConversations.length || !window.confirm('Delete all saved NexorAI conversations? This cannot be undone.')) return;
    history = [];
    savedConversations = [];
    localStorage.removeItem('nexorHistory');
    fetch('/backend/memory/conversations', { method: 'DELETE' }).catch(() => {});
    renderHistory();
};
document.querySelector('.sidebar-footer')?.prepend(dataControls);

/* ── Chat ── */
const chatScroll = document.getElementById('chatScroll');
let welcomeVisible = true;
let activeConversationId = localStorage.getItem(activeConversationStorageKey) || crypto.randomUUID();
localStorage.setItem(activeConversationStorageKey, activeConversationId);

function renderWelcomePrompts() {
    const welcome = document.getElementById('welcomeScreen');
    if (!welcome || welcome.querySelector('.welcome-prompts')) return;
    const prompts = [
        'Help me plan a focused, productive week.',
        'Explain a difficult idea in simple terms.',
        'Review my approach and suggest improvements.'
    ];
    const group = document.createElement('div');
    group.className = 'welcome-prompts';
    group.setAttribute('aria-label', 'Suggested prompts');
    prompts.forEach(prompt => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'welcome-prompt';
        button.textContent = prompt;
        button.onclick = () => {
            const input = document.getElementById('chatInput');
            input.value = prompt;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            window.sendMessage();
        };
        group.appendChild(button);
    });
    welcome.appendChild(group);
}
renderWelcomePrompts();

function openHistoryItem(item) {
    activeConversationId = item.conversationId || crypto.randomUUID();
    localStorage.setItem(activeConversationStorageKey, activeConversationId);
    chatScroll.innerHTML = '';
    welcomeVisible = true;
    const requestedConversation = activeConversationId;
    fetch(`/backend/memory/conversation/${encodeURIComponent(requestedConversation)}`, { cache: 'no-store' }).then(response => response.ok ? response.json() : null).then(result => {
        if (activeConversationId !== requestedConversation) return;
        if (!Array.isArray(result?.data?.conversation?.messages)) {
            renderLocalConversation(requestedConversation);
            return;
        }
        chatScroll.innerHTML = '';
        welcomeVisible = false;
        for (const message of result.data.conversation.messages) {
            appendMessage(message.role, mdToHtml(message.content), { model: message.model, memoryUsed: message.memoryUsed || [] });
        }
    }).catch(() => renderLocalConversation(requestedConversation));
}

function renderLocalConversation(conversationId) {
    if (activeConversationId !== conversationId) return;
    const localTurns = history.filter(turn => turn.conversationId === conversationId);
    chatScroll.innerHTML = '';
    welcomeVisible = true;
    for (const turn of localTurns) {
        appendMessage('user', mdToHtml(turn.user || '[File attached]'));
        appendMessage('bot', mdToHtml(turn.bot || ''), { model: turn.model || currentModel.id, memoryUsed: turn.memoryUsed || [] });
    }
}

function appendMessage(role, htmlContent, details = {}) {
    // Remove welcome screen on first message
    if (welcomeVisible) {
        const ws = document.getElementById('welcomeScreen');
        if (ws) ws.remove();
        welcomeVisible = false;
    }
    const lp = MODEL_LOGOS[currentModel.id];
    const row = document.createElement('div');
    row.className = `msg-row ${role}`;
    
    const avatarHtml = role === 'user'
        ? `<div class="msg-avatar user-av">${userName[0].toUpperCase()}</div>`
        : `<div class="msg-avatar bot-av ${lp?.className || ''}"><img src="${lp?.src || '/static/assets/NexorSplash.png'}" alt="${currentModel.displayName}" style="${lp?.invert ? 'filter:invert(1) brightness(2);' : ''}"></div>`;
    
    row.innerHTML = `${avatarHtml}<div class="msg-content">${htmlContent}</div>`;
    if (role === 'bot' && (details.model || details.memoryUsed?.length || details.fallback)) {
        const badges = document.createElement('div');
        badges.className = 'message-context-badges';
        if (details.model) {
            const modelBadge = document.createElement('span');
            modelBadge.className = 'message-model-badge';
            modelBadge.textContent = MODELS.find(item => item.id === details.model)?.displayName || details.model;
            badges.appendChild(modelBadge);
        }
        if (details.fallback) {
            const fallbackBadge = document.createElement('span');
            fallbackBadge.className = 'message-model-badge';
            fallbackBadge.textContent = 'Fallback model';
            badges.appendChild(fallbackBadge);
        }
        if (details.memoryUsed?.length) {
            const memoryBadge = document.createElement('a');
            memoryBadge.className = 'message-memory-badge';
            memoryBadge.href = '/memory';
            memoryBadge.textContent = `Memory used · ${details.memoryUsed.length}`;
            memoryBadge.title = details.memoryUsed.map(item => item.fact).join('\n');
            badges.appendChild(memoryBadge);
        }
        row.querySelector('.msg-content')?.prepend(badges);
    }
    if (role === 'bot' && !row.querySelector('.typing-dots')) {
        const responseText = row.querySelector('.msg-content').innerText;
        const actions = document.createElement('div');
        actions.className = 'msg-actions';
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'msg-copy';
        copy.textContent = 'Copy';
        copy.setAttribute('aria-label', 'Copy response');
        copy.onclick = async () => {
            try {
                await navigator.clipboard.writeText(responseText);
                copy.textContent = 'Copied';
                window.setTimeout(() => { copy.textContent = 'Copy'; }, 1400);
            } catch {
                copy.textContent = 'Copy unavailable';
            }
        };
        row.querySelector('.msg-content').appendChild(actions);
        actions.appendChild(copy);
    }
    chatScroll.appendChild(row);
    chatScroll.scrollTop = chatScroll.scrollHeight;
    return row;
}

function appendModelComparison(primary, secondary, memoryUsed = []) {
    if (welcomeVisible) {
        document.getElementById('welcomeScreen')?.remove();
        welcomeVisible = false;
    }
    const row = document.createElement('div');
    row.className = 'msg-row bot comparison-row';
    const gridEl = document.createElement('div');
    gridEl.className = 'compare-results';
    for (const answer of [primary, secondary]) {
        const card = document.createElement('article');
        card.className = 'compare-answer';
        const heading = document.createElement('div');
        heading.className = 'compare-answer-head';
        heading.textContent = MODELS.find(item => item.id === answer.model)?.displayName || answer.model;
        const content = document.createElement('div');
        content.className = 'compare-answer-content';
        content.innerHTML = mdToHtml(answer.reply);
        card.append(heading, content);
        if (memoryUsed.length) {
            const memoryBadge = document.createElement('a');
            memoryBadge.href = '/memory';
            memoryBadge.className = 'message-memory-badge';
            memoryBadge.textContent = `Memory used · ${memoryUsed.length}`;
            memoryBadge.title = memoryUsed.map(item => item.fact).join('\n');
            card.appendChild(memoryBadge);
        }
        const copy = document.createElement('button');
        copy.type = 'button'; copy.className = 'msg-copy'; copy.textContent = 'Copy';
        copy.onclick = async () => { try { await navigator.clipboard.writeText(answer.reply); copy.textContent = 'Copied'; } catch { copy.textContent = 'Copy unavailable'; } };
        card.appendChild(copy);
        gridEl.appendChild(card);
    }
    row.appendChild(gridEl);
    chatScroll.appendChild(row);
    chatScroll.scrollTop = chatScroll.scrollHeight;
}

function mdToHtml(text) {
    const escaped = String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    const codeBlocks = [];
    const withPlaceholders = escaped.replace(/```([\w-]*)\n?([\s\S]*?)```/g, (_, language, code) => {
        const safeLanguage = String(language || '').toLowerCase();
        const className = safeLanguage ? ` class="language-${safeLanguage}"` : '';
        codeBlocks.push(`<pre><code${className}>${highlightCode(code.trimEnd(), safeLanguage)}</code></pre>`);
        return `\u0000${codeBlocks.length - 1}\u0000`;
    });
    return withPlaceholders
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^\s*(#{1,6})\s+(.+)$/gm, (_, hashes, heading) => `<h${hashes.length}>${heading.trim()}</h${hashes.length}>`)
        .replace(/^\s*[-*]\s+(.+)$/gm, '<li>$1</li>')
        .replace(/\n{2,}/g, '<br><br>')
        .replace(/\n/g, '<br>')
        .replace(/\u0000(\d+)\u0000/g, (_, index) => codeBlocks[Number(index)]);
}

// Highlight escaped code in place so syntax colors never introduce executable HTML.
function highlightCode(code, language) {
    const commentPattern = /^(?:javascript|js|typescript|ts|jsx|tsx|java|c|cpp|c\+\+|csharp|cs|go|rust|swift|kotlin|php|css|scss)$/.test(language)
        ? /\/\/[^\n]*|\/\*[\s\S]*?\*\//
        : /^(?:python|py|ruby|bash|sh|shell|yaml|yml|toml|r|julia)$/.test(language)
            ? /#[^\n]*/
            : /(?!) /;
    const tokenPattern = new RegExp(
        `(${commentPattern.source})|(&quot;&quot;&quot;[\\s\\S]*?&quot;&quot;&quot;|&#39;&#39;&#39;[\\s\\S]*?&#39;&#39;&#39;|&quot;.*?&quot;|&#39;.*?&#39;)|(\\b(?:const|let|var|function|return|if|else|for|while|class|new|this|async|await|import|from|export|default|try|catch|throw|public|private|static|void|int|float|bool|true|false|null|undefined|None|True|False|def|print|in|of|extends|interface|type|enum|switch|case|break|continue|yield|lambda|pass|with|as|finally|elif|super|self)\\b)|(\\b\\d+(?:\\.\\d+)?\\b)|(\\b[A-Za-z_$][\\w$]*(?=\\s*\\())|(\\b[A-Za-z_$][\\w$]*\\b)|(\\s+|.)`, 'g'
    );
    return code.replace(tokenPattern, (token, comment, string, keyword, number, callableName, identifier) => {
        const kind = comment ? 'comment' : string ? 'string' : keyword ? 'keyword' : number ? 'number' : callableName ? 'function' : identifier && /^(?:true|false|null|undefined|None|True|False)$/.test(identifier) ? 'literal' : identifier ? 'identifier' : '';
        return kind ? `<span class="syntax-${kind}">${token}</span>` : token;
    });
}

let pendingAttachments = [];

window.handleAttach = function(e, type) {
    const file = e.target.files[0];
    if (!file) return;
    pendingAttachments.push({ name: file.name, type });
    const bar = document.getElementById('attachBar');
    const chip = document.createElement('div');
    chip.className = 'attach-chip';
    chip.dataset.name = file.name;
    chip.innerHTML = `${type === 'image' ? '🖼' : '📎'} ${file.name} <span class="rm" onclick="removeAttach('${file.name}', this.parentElement)">×</span>`;
    bar.appendChild(chip);
    e.target.value = '';
};

window.removeAttach = function(name, el) {
    pendingAttachments = pendingAttachments.filter(a => a.name !== name);
    el.remove();
};

document.getElementById('chatInput').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

window.sendMessage = async () => {
    const inp = document.getElementById('chatInput');
    const text = inp.value.trim();
    const hasAttachments = pendingAttachments.length > 0;
    if (!text && !hasAttachments) return;

    inp.value = '';
    inp.style.height = 'auto';
    document.getElementById('sendBtn').disabled = true;

    // Show user message
    let userHtml = text ? mdToHtml(text) : '';
    if (hasAttachments) {
        userHtml += pendingAttachments.map(a => `<div style="margin-top:8px; font-size:12px; color:var(--muted);">${a.type === 'image' ? '🖼' : '📎'} ${a.name}</div>`).join('');
        document.getElementById('attachBar').innerHTML = '';
        pendingAttachments = [];
    }
    appendMessage('user', userHtml);

    // Loading row
    const loadRow = appendMessage('bot', '<div class="typing-dots"><span></span><span></span><span></span></div>');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text || '[File attached]', model: currentModel.id, conversationId: activeConversationId, compareWith: compareModelSelect.value || undefined })
        });
        if (res.status === 401) { window.location.href = '/login'; return; }
        const data = await res.json();
        loadRow.remove();
        if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);
        activeConversationId = data.conversationId || activeConversationId;
        localStorage.setItem(activeConversationStorageKey, activeConversationId);
        if (data.comparison) appendModelComparison({ model: data.model, reply: data.reply }, data.comparison, data.memoryUsed || []);
        else appendMessage('bot', mdToHtml(data.reply), { model: data.model, fallback: data.fallback, memoryUsed: data.memoryUsed });
        history.push({ user: text, bot: data.reply, model: data.model, memoryUsed: data.memoryUsed, conversationId: activeConversationId, title: text || '[Attachment]' });
        localStorage.setItem('nexorHistory', JSON.stringify(history));
        renderHistory();
        void refreshSavedConversations();
    } catch(err) {
        loadRow.remove();
        appendMessage('bot', `<span style="color:#F87171;">⚠ ${err.message}</span>`);
    }

    document.getElementById('sendBtn').disabled = false;
    inp.focus();
};

window.startNewChat = async () => {
    toggleSidebar(false);
    activeConversationId = crypto.randomUUID();
    localStorage.setItem(activeConversationStorageKey, activeConversationId);
    chatScroll.innerHTML = `<div class="welcome" id="welcomeScreen">
        <img src="/static/assets/NexorSplash.png" alt="NexorAI">
        <h2>How can I help you today?</h2>
        <p>Powered by Gemini Flash — fast, capable, and intelligent.</p>
    </div>`;
    renderWelcomePrompts();
    welcomeVisible = true;
    document.getElementById('attachBar').innerHTML = '';
    pendingAttachments = [];
};
