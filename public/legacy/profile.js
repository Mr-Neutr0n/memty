const MAX_AVATAR_DATA_LENGTH = 80000;

export function setupProfile({ getUser, onUpdated }) {
    const trigger = document.getElementById('userBtn');
    if (!trigger) return;

    trigger.removeAttribute('onclick');

    const overlay = document.createElement('div');
    overlay.className = 'profile-overlay';
    overlay.id = 'profileOverlay';
    overlay.innerHTML = `
        <section class="profile-dialog" role="dialog" aria-modal="true" aria-labelledby="profileTitle">
            <aside class="profile-rail">
                <div class="profile-rail-brand"><span class="profile-brand-mark">N</span><span>Memty</span></div>
                <div class="profile-rail-account">
                    <div class="profile-avatar" id="profileAvatar">U</div>
                    <div><strong id="profileRailName">Your account</strong><span id="profileRailEmail"></span></div>
                </div>
                <nav class="profile-tabs" aria-label="Account settings">
                    <button type="button" class="profile-tab active" data-profile-tab="profile"><span>◉</span> Profile</button>
                    <button type="button" class="profile-tab" data-profile-tab="billing"><span>▤</span> Billing</button>
                    <button type="button" class="profile-tab" data-profile-tab="settings"><span>⚙</span> Settings</button>
                </nav>
                <div class="profile-rail-spacer"></div>
                <p class="profile-rail-caption">Your account, your choices.</p>
                <button type="button" class="profile-signout" id="profileSignout"><span>↪</span> Sign out</button>
            </aside>
            <div class="profile-content">
                <header class="profile-header">
                    <div><p class="profile-eyebrow">ACCOUNT SETTINGS</p><h2 id="profileTitle">Your profile</h2></div>
                    <button type="button" class="profile-close" aria-label="Close profile">×</button>
                </header>
                <div class="profile-status" id="profileStatus" role="status" aria-live="polite"></div>
                <section class="profile-panel" data-profile-panel="profile">
                    <div class="profile-welcome-card"><div><span class="profile-welcome-kicker">YOUR MEMTY SPACE</span><h3>Make it yours.</h3><p>Personalize your account details and the way Memty recognizes you.</p></div><div class="profile-orbit">✦</div></div>
                    <form id="profileForm" class="profile-form">
                        <div class="profile-photo-row">
                            <div class="profile-avatar profile-avatar-large" id="profilePhotoPreview">U</div>
                            <div class="profile-photo-copy"><strong>Profile photo</strong><p>JPG, PNG, or WebP. We resize it before saving.</p><div class="profile-photo-actions"><button type="button" class="profile-secondary-button" id="profileUpload">Upload photo</button><button type="button" class="profile-text-button" id="profileRemovePhoto">Remove</button></div></div>
                            <input type="file" id="profilePhotoInput" accept="image/jpeg,image/png,image/webp" hidden>
                        </div>
                        <div class="profile-form-grid">
                            <label class="profile-field profile-field-wide"><span>Full name</span><input id="profileName" name="name" autocomplete="name" minlength="2" maxlength="100" required></label>
                            <label class="profile-field profile-field-wide"><span>Email address</span><input id="profileEmail" name="email" type="email" readonly><small>Your email is managed by your sign-in method.</small></label>
                            <label class="profile-field"><span>Date of birth</span><input id="profileDOB" name="DOB" type="date" max=""></label>
                            <div class="profile-field"><span>Age</span><div class="profile-age-value" id="profileAge">Not set</div><small>Calculated from your date of birth.</small></div>
                        </div>
                        <div class="profile-form-footer"><span>Your profile is private to your account.</span><button type="submit" class="profile-primary-button" id="profileSave">Save changes</button></div>
                    </form>
                </section>
                <section class="profile-panel" data-profile-panel="billing" hidden>
                    <div class="billing-heading"><div><span class="profile-welcome-kicker">MEMTY BILLING</span><h3>Plan and payments</h3><p>Manage your plan and choose how you’d prefer to pay when Pro launches.</p></div></div>
                    <article class="billing-plan-card"><div class="billing-plan-icon">✦</div><div class="billing-plan-copy"><span class="billing-plan-label">CURRENT PLAN</span><h4 id="billingPlanName">Free plan</h4><p>Pro subscriptions are being prepared and are not available yet.</p></div><span class="billing-plan-status">ACTIVE</span></article>
                    <div class="billing-section-title"><div><h4>Preferred payment method</h4><p>This saves a preference only. No payment details are collected.</p></div><span class="billing-soon-pill">CHECKOUT SOON</span></div>
                    <div class="billing-methods" role="radiogroup" aria-label="Preferred payment method">
                        <button type="button" class="billing-method" data-payment-method="upi" role="radio" aria-checked="false"><span class="billing-method-icon">₹</span><span><strong>UPI</strong><small>UPI apps and payment handles</small></span><span class="billing-radio"></span></button>
                        <button type="button" class="billing-method" data-payment-method="card" role="radio" aria-checked="false"><span class="billing-method-icon">▤</span><span><strong>Credit or debit card</strong><small>Card checkout when billing launches</small></span><span class="billing-radio"></span></button>
                    </div>
                    <div class="billing-notice"><span>ⓘ</span><p>Payments are not active yet. Choosing a preference will not start a subscription, store UPI or card details, or charge you.</p></div>
                    <div class="profile-form-footer billing-footer"><span id="billingPreferenceLabel">No preference selected</span><button type="button" class="profile-primary-button" id="billingSave">Save preference</button></div>
                </section>
                <section class="profile-panel" data-profile-panel="settings" hidden>
                    <div class="billing-heading"><div><span class="profile-welcome-kicker">YOUR DATA</span><h3>Chat history</h3><p>Take a copy of your conversations or clear chat history saved in this browser.</p></div></div>
                    <article class="settings-data-card"><div><strong>Export chat history</strong><p>Download your saved conversations as a JSON file.</p></div><button type="button" class="profile-secondary-button" id="exportChats">Export chats</button></article>
                    <article class="settings-data-card settings-danger-card"><div><strong>Delete all local chats</strong><p>Remove saved conversations from this browser. This cannot be undone.</p></div><button type="button" class="profile-danger-button" id="deleteChats">Delete all</button></article>
                </section>
            </div>
        </section>`;
    document.body.appendChild(overlay);

    let selectedAvatarData = '';
    let selectedPaymentMethod = '';
    let currentUser = getUser() || {};
    const status = overlay.querySelector('#profileStatus');
    const profileName = overlay.querySelector('#profileName');
    const profileEmail = overlay.querySelector('#profileEmail');
    const profileDOB = overlay.querySelector('#profileDOB');
    const photoInput = overlay.querySelector('#profilePhotoInput');
    const now = new Date();
    profileDOB.max = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

    function report(message = '', type = '') {
        status.textContent = message;
        status.className = `profile-status${type ? ` ${type}` : ''}`;
    }

    function setAvatar(element, user) {
        element.replaceChildren();
        if (user.avatarData) {
            const image = document.createElement('img');
            image.src = user.avatarData;
            image.alt = 'Profile photo';
            element.appendChild(image);
        } else {
            element.textContent = (user.name || user.email || 'U').trim().charAt(0).toUpperCase() || 'U';
        }
    }

    function ageFromDate(value) {
        if (!value) return 'Not set';
        const [year, month, day] = value.split('-').map(Number);
        const today = new Date();
        let age = today.getFullYear() - year;
        if (today.getMonth() + 1 < month || (today.getMonth() + 1 === month && today.getDate() < day)) age--;
        return age >= 0 ? `${age} years` : 'Not set';
    }

    function renderUser(user) {
        currentUser = user || {};
        profileName.value = currentUser.name || '';
        profileEmail.value = currentUser.email || '';
        profileDOB.value = currentUser.DOB || '';
        overlay.querySelector('#profileAge').textContent = ageFromDate(profileDOB.value);
        overlay.querySelector('#profileRailName').textContent = currentUser.name || 'Your account';
        overlay.querySelector('#profileRailEmail').textContent = currentUser.email || '';
        overlay.querySelector('#billingPlanName').textContent = currentUser.plan === 'pro' ? 'Pro plan' : 'Free plan';
        setAvatar(overlay.querySelector('#profileAvatar'), currentUser);
        setAvatar(overlay.querySelector('#profilePhotoPreview'), currentUser);
        selectedAvatarData = currentUser.avatarData || '';
        selectedPaymentMethod = currentUser.preferredPaymentMethod || '';
        updatePaymentSelection();
    }

    function updatePaymentSelection() {
        overlay.querySelectorAll('[data-payment-method]').forEach(button => {
            const selected = button.dataset.paymentMethod === selectedPaymentMethod;
            button.classList.toggle('selected', selected);
            button.setAttribute('aria-checked', String(selected));
        });
        overlay.querySelector('#billingPreferenceLabel').textContent = selectedPaymentMethod
            ? `Preferred method: ${selectedPaymentMethod === 'upi' ? 'UPI' : 'Credit or debit card'}`
            : 'No preference selected';
    }

    function switchTab(tab) {
        overlay.querySelectorAll('[data-profile-tab]').forEach(button => button.classList.toggle('active', button.dataset.profileTab === tab));
        overlay.querySelectorAll('[data-profile-panel]').forEach(panel => { panel.hidden = panel.dataset.profilePanel !== tab; });
        overlay.querySelector('#profileTitle').textContent = ({ billing: 'Billing', settings: 'Settings' })[tab] || 'Your profile';
        report();
    }

    async function refreshUser() {
        const response = await fetch('/users/me', { cache: 'no-store', credentials: 'same-origin' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.data?.user) throw new Error(data.message || data.error || 'Could not load your profile.');
        renderUser(data.data.user);
        onUpdated(data.data.user);
    }

    async function saveProfile(event) {
        event.preventDefault();
        const button = overlay.querySelector('#profileSave');
        button.disabled = true;
        button.textContent = 'Saving…';
        report();
        try {
            const response = await fetch('/users/me', {
                method: 'PATCH', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: profileName.value, DOB: profileDOB.value, avatarData: selectedAvatarData })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.data?.user) throw new Error(data.message || data.error || 'Could not save your profile.');
            renderUser(data.data.user);
            onUpdated(data.data.user);
            report('Your profile has been saved.', 'success');
        } catch (error) {
            report(error instanceof Error ? error.message : 'Could not save your profile.', 'error');
        } finally {
            button.disabled = false;
            button.textContent = 'Save changes';
        }
    }

    async function saveBillingPreference() {
        const button = overlay.querySelector('#billingSave');
        button.disabled = true;
        button.textContent = 'Saving…';
        report();
        try {
            const response = await fetch('/users/me', {
                method: 'PATCH', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ preferredPaymentMethod: selectedPaymentMethod })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.data?.user) throw new Error(data.message || data.error || 'Could not save your preference.');
            renderUser(data.data.user);
            onUpdated(data.data.user);
            report('Payment preference saved. Checkout is not active yet.', 'success');
        } catch (error) {
            report(error instanceof Error ? error.message : 'Could not save your preference.', 'error');
        } finally {
            button.disabled = false;
            button.textContent = 'Save preference';
        }
    }

    async function compressAvatar(file) {
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('Choose a JPG, PNG, or WebP image.');
        if (file.size > 10 * 1024 * 1024) throw new Error('Choose an image smaller than 10 MB.');
        const bitmap = await createImageBitmap(file);
        const side = Math.min(bitmap.width, bitmap.height);
        const sx = Math.floor((bitmap.width - side) / 2);
        const sy = Math.floor((bitmap.height - side) / 2);
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Could not process this image.');
        for (const size of [256, 192, 160]) {
            canvas.width = size;
            canvas.height = size;
            context.clearRect(0, 0, size, size);
            context.drawImage(bitmap, sx, sy, side, side, 0, 0, size, size);
            for (const quality of [0.82, 0.68, 0.54, 0.4]) {
                const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/webp', quality));
                if (!blob) continue;
                const encoded = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(reader.result);
                    reader.onerror = () => reject(new Error('Could not read the resized image.'));
                    reader.readAsDataURL(blob);
                });
                if (typeof encoded === 'string' && encoded.length <= MAX_AVATAR_DATA_LENGTH) {
                    bitmap.close();
                    return encoded;
                }
            }
        }
        bitmap.close();
        throw new Error('This image could not be compressed small enough. Try a simpler image.');
    }

    function close() {
        overlay.classList.remove('open');
        trigger.focus();
    }

    trigger.addEventListener('click', () => {
        renderUser(getUser() || currentUser);
        overlay.classList.toggle('light', document.querySelector('.legacy-page-chat')?.classList.contains('light') || false);
        overlay.classList.add('open');
        void refreshUser().catch(error => report(error instanceof Error ? error.message : 'Could not load your profile.', 'error'));
        overlay.querySelector('.profile-close').focus();
    });
    overlay.querySelector('.profile-close').addEventListener('click', close);
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && overlay.classList.contains('open')) close(); });
    overlay.querySelectorAll('[data-profile-tab]').forEach(button => button.addEventListener('click', () => switchTab(button.dataset.profileTab)));
    overlay.querySelector('#profileForm').addEventListener('submit', saveProfile);
    profileDOB.addEventListener('change', () => { overlay.querySelector('#profileAge').textContent = ageFromDate(profileDOB.value); });
    overlay.querySelector('#profileUpload').addEventListener('click', () => photoInput.click());
    overlay.querySelector('#profileRemovePhoto').addEventListener('click', () => {
        selectedAvatarData = '';
        setAvatar(overlay.querySelector('#profilePhotoPreview'), { name: profileName.value });
        photoInput.value = '';
        report('Photo removed. Save changes to apply it.', '');
    });
    photoInput.addEventListener('change', async () => {
        if (!photoInput.files?.[0]) return;
        try {
            selectedAvatarData = await compressAvatar(photoInput.files[0]);
            setAvatar(overlay.querySelector('#profilePhotoPreview'), { name: profileName.value, avatarData: selectedAvatarData });
            report('Photo ready. Save changes to apply it.', 'success');
        } catch (error) {
            report(error instanceof Error ? error.message : 'Could not process this image.', 'error');
        }
    });
    overlay.querySelectorAll('[data-payment-method]').forEach(button => button.addEventListener('click', () => {
        selectedPaymentMethod = button.dataset.paymentMethod;
        updatePaymentSelection();
        report('This preference is not a payment or subscription.', '');
    }));
    overlay.querySelector('#billingSave').addEventListener('click', saveBillingPreference);
    overlay.querySelector('#exportChats').addEventListener('click', () => {
        if (typeof window.exportLocalChats === 'function') window.exportLocalChats();
        else report('Chat history is not ready to export.', 'error');
    });
    overlay.querySelector('#deleteChats').addEventListener('click', () => {
        if (typeof window.deleteLocalChats === 'function') window.deleteLocalChats(message => report(message, 'success'));
        else report('Chat history is not ready to delete.', 'error');
    });
    overlay.querySelector('#profileSignout').addEventListener('click', () => window.logout());
    renderUser(currentUser);
}
