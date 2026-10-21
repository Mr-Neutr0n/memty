(() => {
if (localStorage.getItem('nexoraiUser')) {
    fetch('/users/me', { cache: 'no-store' }).then(response => {
        if (response.ok) window.location.href = '/chatbot';
        else localStorage.removeItem('nexoraiUser');
    }).catch(() => {});
}

        let mode = 'login';

        window.setMode = function(m) {
            mode = m;
            const isSignup = m === 'signup';
            document.getElementById('loginTab').classList.toggle('active', !isSignup);
            document.getElementById('signupTab').classList.toggle('active', isSignup);
            document.getElementById('nameGroup').style.display = isSignup ? 'block' : 'none';
            document.getElementById('dobGroup').style.display = isSignup ? 'block' : 'none';
            document.getElementById('name').required = isSignup;
            document.getElementById('dob').required = isSignup;
            document.getElementById('btnText').textContent = isSignup ? 'Create Account' : 'Sign In';
            document.getElementById('switchText').textContent = isSignup ? 'Already have an account?' : "Don't have an account?";
            document.getElementById('switchLink').textContent = isSignup ? 'Sign in' : 'Create one';
            document.getElementById('switchLink').onclick = () => setMode(isSignup ? 'login' : 'signup');
            document.getElementById('statusMsg').className = 'status-msg';
        };

        let googleSignInReady = false;
        let googleSignInBusy = false;

        window.handleGoogle = function() {
            showStatus(googleSignInReady ? 'Use the Google sign-in button above.' : 'Google sign-in is still loading. Please try again shortly.', 'error');
        };

        function loadGoogleIdentityServices() {
            if (window.google?.accounts?.id) return Promise.resolve();
            return new Promise((resolve, reject) => {
                const existing = document.querySelector('script[data-google-identity-services]');
                if (existing) {
                    existing.addEventListener('load', resolve, { once: true });
                    existing.addEventListener('error', () => reject(new Error('Could not load Google sign-in.')), { once: true });
                    return;
                }
                const script = document.createElement('script');
                script.src = 'https://accounts.google.com/gsi/client';
                script.async = true;
                script.defer = true;
                script.dataset.googleIdentityServices = 'true';
                script.onload = () => resolve();
                script.onerror = () => reject(new Error('Could not load Google sign-in.'));
                document.head.appendChild(script);
            });
        }

        async function completeGoogleSignIn(response) {
            if (googleSignInBusy) return;
            if (typeof response?.credential !== 'string') {
                showStatus('Google did not return a sign-in credential. Please try again.', 'error');
                return;
            }
            googleSignInBusy = true;
            const button = document.getElementById('googleSignInButton');
            if (button) button.style.pointerEvents = 'none';
            showStatus('Signing you in with Google…', '');
            try {
                const result = await fetch('/users/google', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({ credential: response.credential })
                });
                const data = await result.json().catch(() => ({}));
                if (!result.ok) throw new Error(data.message || data.error || 'Google sign-in failed.');
                const user = data.data?.user;
                if (!user) throw new Error('Google sign-in completed without an account response.');
                localStorage.setItem('nexoraiUser', JSON.stringify(user));
                showStatus('Success! Redirecting…', 'success');
                window.location.assign('/chatbot');
            } catch (error) {
                showStatus(error instanceof Error ? error.message : 'Google sign-in failed. Please try again.', 'error');
            } finally {
                googleSignInBusy = false;
                if (button) button.style.pointerEvents = '';
            }
        }

        async function setupGoogleSignIn() {
            const currentButton = document.querySelector('.google-btn');
            if (!currentButton) return;
            try {
                const configResponse = await fetch('/api/config', { cache: 'no-store' });
                const config = await configResponse.json().catch(() => ({}));
                if (!configResponse.ok || typeof config.googleClientId !== 'string' || !config.googleClientId) {
                    throw new Error('Google sign-in is not configured. You can still use email and password.');
                }
                await loadGoogleIdentityServices();
                window.google.accounts.id.initialize({
                    client_id: config.googleClientId,
                    callback: completeGoogleSignIn,
                    auto_select: false,
                    cancel_on_tap_outside: true
                });
                const googleButton = document.createElement('div');
                googleButton.id = 'googleSignInButton';
                googleButton.className = 'google-btn google-sign-in-container';
                googleButton.setAttribute('aria-label', 'Continue with Google');
                currentButton.replaceWith(googleButton);
                window.google.accounts.id.renderButton(googleButton, {
                    type: 'standard', theme: 'outline', size: 'large', text: 'continue_with', shape: 'rectangular',
                    width: Math.min(400, Math.max(200, Math.floor(googleButton.clientWidth)))
                });
                googleSignInReady = true;
            } catch (error) {
                currentButton.disabled = true;
                currentButton.title = error instanceof Error ? error.message : 'Google sign-in is unavailable.';
                showStatus(currentButton.title, 'error');
            }
        }

        setupGoogleSignIn();

        window.handleSubmit = async function(e) {
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            const spinner = document.getElementById('spinner');
            const btnText = document.getElementById('btnText');
            
            btn.disabled = true;
            btnText.style.display = 'none';
            spinner.style.display = 'block';
            document.getElementById('statusMsg').className = 'status-msg';

            const payload = mode === 'login'
                ? { email: document.getElementById('email').value, password: document.getElementById('password').value }
                : { name: document.getElementById('name').value, email: document.getElementById('email').value, password: document.getElementById('password').value, DOB: document.getElementById('dob').value };

            try {
                const res = await fetch(mode === 'login' ? '/users/login' : '/users/signup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                let data = {};
                try { data = await res.json(); } catch(err) {}
                if (!res.ok) throw new Error(data.message || data.error || 'Authentication failed');
                localStorage.setItem('nexoraiUser', JSON.stringify(data.data?.user || { email: payload.email }));
                showStatus('Success! Redirecting…', 'success');
                setTimeout(() => window.location.href = '/chatbot', 1000);
            } catch(err) {
                showStatus(err.message, 'error');
                btn.disabled = false;
                btnText.style.display = 'block';
                spinner.style.display = 'none';
            }
        };

        function showStatus(msg, type) {
            const el = document.getElementById('statusMsg');
            el.textContent = msg;
            el.className = `status-msg ${type}`;
        }
})();
