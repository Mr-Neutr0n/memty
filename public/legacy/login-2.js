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

        window.handleGoogle = function() {
            showStatus('Google OAuth requires backend configuration. Use email/password for now.', 'error');
        };

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
