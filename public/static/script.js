// Redirect to login if no token
const signedInUser = localStorage.getItem('nexoraiUser');
// Temporarily disabled to allow access without login
if (!signedInUser) {
    window.location.href = '/login';
}

const chat = document.getElementById('chat');
const input = document.getElementById('input');
const send = document.getElementById('send');
const fileInput = document.getElementById('fileInput');
const proBtn = document.getElementById('proBtn');
const historyBtn = document.getElementById('historyBtn');
const proModal = document.getElementById('proModal');
const historyPanel = document.getElementById('historyPanel');
const closeHistory = document.getElementById('closeHistory');
const searchHistory = document.getElementById('searchHistory');
const historyList = document.getElementById('historyList');
const purchasePro = document.getElementById('purchasePro');
// Remove modeRadios, chatbotMode, and related event listeners

// Chat history storage
let chatHistory = JSON.parse(localStorage.getItem('chatHistory') || '[]');
let isPro = false;

// Update Pro button text
function updateProButton() {
    proBtn.textContent = isPro ? 'Pro User Ã¢Å“â€œ' : 'Upgrade to Pro';
    proBtn.style.background = isPro ? '#28a745' : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
}

updateProButton();

function appendMessage(sender, text, isFile = false) {
    const div = document.createElement('div');
    div.className = `bubble ${sender}`;

    if (isFile) {
        div.innerHTML = `<span style="font-size: 0.9rem;">Ã°Å¸â€œÅ½ ${text}</span>`;
    } else {
        div.textContent = text;
    }

    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function setLoading(isLoading) {
    if (isLoading) {
        appendMessage('bot', '...');
    } else {
        const bubbles = chat.getElementsByClassName('bubble');
        if (bubbles.length && bubbles[bubbles.length - 1].textContent === '...') {
            chat.removeChild(bubbles[bubbles.length - 1]);
        }
    }
}

function saveToHistory(userMessage, botResponse) {
    chatHistory.push({
        user: userMessage,
        bot: botResponse,
        timestamp: new Date().toISOString()
    });
    localStorage.setItem('chatHistory', JSON.stringify(chatHistory));
}

function displayHistory(searchTerm = '') {
    historyList.innerHTML = '';
    const filteredHistory = chatHistory.filter(item =>
        item.user.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.bot.toLowerCase().includes(searchTerm.toLowerCase())
    );

    filteredHistory.reverse().forEach(item => {
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        historyItem.innerHTML = `
            <div class="user-msg">${item.user.substring(0, 50)}${item.user.length > 50 ? '...' : ''}</div>
            <div class="bot-msg">${item.bot.substring(0, 100)}${item.bot.length > 100 ? '...' : ''}</div>
        `;
        historyItem.onclick = () => {
            appendMessage('user', item.user);
            appendMessage('bot', item.bot);
            historyPanel.classList.add('hidden');
        };
        historyList.appendChild(historyItem);
    });
}

// Chat functionality
send.onclick = async function () {
    const message = input.value.trim();
    if (!message) return;

    appendMessage('user', message);
    input.value = '';
    setLoading(true);

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message })
        });

        // If token is invalid/expired, go back to login
        if (res.status === 401) {
            window.location.href = '/login';
        }
        let data;
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            data = await res.json();
        } else {
            const text = await res.text();
            data = {
                error: text || `Request failed with status ${res.status}`
            };
        }

        if (!res.ok) {
            throw new Error(data.error || data.message || `Request failed with status ${res.status}`);
        }

        setLoading(false);
        const response = data.reply || data.error || 'Something went wrong.';
        appendMessage('bot', response);
        saveToHistory(message, response);
    } catch (e) {
        setLoading(false);
        appendMessage('bot', e.message || 'Error connecting to server.');
    }
};

// File attachment
fileInput.onchange = function (e) {
    const file = e.target.files[0];
    if (file) {
        if (!isPro) {
            alert('File attachments are only available for Pro users. Please upgrade to Pro.');
            return;
        }
        appendMessage('user', `Attached: ${file.name}`, true);
        // In a real app, you'd upload the file to the server here
        appendMessage('bot', `I can see you've attached "${file.name}". In a full implementation, I would process this file for you.`);
        saveToHistory(`Attached: ${file.name}`, `I can see you've attached "${file.name}". In a full implementation, I would process this file for you.`);
    }
};

// Pro modal
proBtn.onclick = function () {
    if (isPro) {
        alert('You are already a Pro user!');
        return;
    }
    proModal.classList.remove('hidden');
};

// Close modal when clicking outside
proModal.onclick = function (e) {
    if (e.target === proModal) {
        proModal.classList.add('hidden');
    }
};

// Close button
document.querySelector('.close').onclick = function () {
    proModal.classList.add('hidden');
};

// Purchase Pro (demo)
purchasePro.onclick = function () {
    proModal.classList.add('hidden');
    appendMessage('bot', 'Premium plans are coming soon. Core chat and workspace features are available now.');
};

// History panel
historyBtn.onclick = function () {
    historyPanel.classList.remove('hidden');
    displayHistory();
};

closeHistory.onclick = function () {
    historyPanel.classList.add('hidden');
};

// Close history panel when clicking outside
historyPanel.onclick = function (e) {
    if (e.target === historyPanel) {
        historyPanel.classList.add('hidden');
    }
};

// Search history
searchHistory.oninput = function () {
    displayHistory(this.value);
};

// Keyboard shortcuts
input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
        send.onclick();
    }
});

// Welcome message for Pro users
if (isPro) {
    setTimeout(() => {
        appendMessage('bot', 'Welcome back, Pro user! You have access to all advanced features.');
    }, 1000);
} 
