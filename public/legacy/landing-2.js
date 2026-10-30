(function() {
    const canvas = document.getElementById('orrery');
    const ctx = canvas.getContext('2d');
    const DPR = window.devicePixelRatio || 1;

    let W, H, cx, cy;

    function resize() {
        const cssW = canvas.parentElement.clientWidth;
        const cssH = Math.round(Math.max(500, cssW * 0.66));
        canvas.style.width  = cssW + 'px';
        canvas.style.height = cssH + 'px';
        canvas.width  = cssW * DPR;
        canvas.height = cssH * DPR;
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        W = cssW; H = cssH;
        cx = W / 2; cy = H * 0.48;
    }
    resize();
    window.addEventListener('resize', resize);

    /* ---------- Image loading ---------- */
    const SRC = {
        nexor:  '/static/assets/NexorSplash.png',
        claude: '/static/assets/claude.png',
        meta:   '/static/assets/meta.png',
        gemini: '/static/assets/gemini.png',
        nvidia: '/static/assets/nvdia.jpg',
        openai: '/static/assets/openai.jpg',
        grok:   '/static/assets/groak.webp'
    };
    const IMGS = {};
    let loaded = 0;
    const total = Object.keys(SRC).length;
    Object.entries(SRC).forEach(([k, src]) => {
        const img = new Image();
        img.onload = img.onerror = () => { IMGS[k] = img.complete ? img : null; if(++loaded === total) startLoop(); };
        img.src = src;
    });

    /* ---------- Planet definitions ---------- */
    // TILT: y-scale factor — makes orbits look like tilted ellipses (3D)
    const TILT = 0.38;

    const PLANETS = [
        { key:'claude', name:'Claude Sonnet',   sub:'Anthropic',  avail:false, orbit:0.18, speed:0.42, angle:0.0,  border:'#E5894A', logoWhiteBg:true  },
        { key:'meta',   name:'Meta Llama',       sub:'Meta',       avail:false, orbit:0.34, speed:0.27, angle:2.1,  border:'#1877F2', logoWhiteBg:true  },
        { key:'gemini', name:'Gemini Flash',     sub:'Google',     avail:true,  orbit:0.50, speed:0.17, angle:4.6,  border:'#7C6AFA', logoWhiteBg:false },
        { key:'nvidia', name:'NVIDIA Nemotron', sub:'NVIDIA', avail:true, orbit:0.66, speed:0.10, angle:1.4, border:'#76B900', logoWhiteBg:true  },
        { key:'openai', name:'ChatGPT',          sub:'OpenAI',  avail:true, orbit:0.76, speed:0.085, angle:5.2, border:'#10A37F', logoWhiteBg:true  },
        { key:'grok',   name:'Grok AI',           sub:'xAI',        avail:false, orbit:0.82, speed:0.07, angle:3.2,  border:'#E5E7EB', logoWhiteBg:true  },
    ];

    /* ---------- Main loop ---------- */
    let last = 0;
    function startLoop() { requestAnimationFrame(loop); }

    function loop(ts) {
        requestAnimationFrame(loop);
        const dt = Math.min((ts - last) / 1000, 0.05);
        last = ts;

        PLANETS.forEach(p => { p.angle = (p.angle + p.speed * dt) % (Math.PI * 2); });

        const orbitMax = Math.min(W * 0.47, (H - 130) / TILT);
        PLANETS.forEach(p => { p.rx = Math.max(58, orbitMax * p.orbit); });

        ctx.clearRect(0, 0, W, H);

        /* Orbit ellipses */
        PLANETS.forEach(p => {
            ctx.save();
            ctx.beginPath();
            ctx.ellipse(cx, cy, p.rx, p.rx * TILT, 0, 0, Math.PI * 2);
            ctx.strokeStyle = 'rgba(190,198,255,0.62)';
            ctx.lineWidth = 1.5;
            ctx.shadowBlur = 7;
            ctx.shadowColor = 'rgba(130,145,255,0.35)';
            ctx.setLineDash([4, 5]);
            ctx.stroke();
            ctx.shadowBlur = 0;
            ctx.setLineDash([]);
            ctx.restore();
        });

        /* Compute positions + depth sort (painter's algorithm) */
        const objs = PLANETS.map(p => {
            const px = cx + Math.cos(p.angle) * p.rx;
            const py = cy + Math.sin(p.angle) * p.rx * TILT;
            const sin = Math.sin(p.angle); // -1=back, +1=front
            const depth01 = (sin + 1) / 2;
            const scale = 0.68 + 0.44 * depth01;
            const alpha = 0.78 + 0.22 * depth01;
            return { ...p, px, py, scale, alpha, sin };
        }).sort((a, b) => a.sin - b.sin); // back first

        drawMemoryTransfers(objs, ts);

        objs.forEach(o => drawPlanet(o));

        /* Sun always on top */
        drawSun();
    }

    /* ---------- Shared-memory transfer paths ---------- */
    function drawMemoryTransfers(planets, timestamp) {
        const byKey = new Map(planets.map(planet => [planet.key, planet]));
        // A subtle ring connects the models while packets move through one link at a time.
        const routes = [
            ['claude', 'meta'],
            ['meta', 'gemini'],
            ['gemini', 'nvidia'],
            ['nvidia', 'openai'],
            ['openai', 'grok'],
            ['grok', 'claude']
        ];
        const cycleMs = 9000;
        const activeMs = 1050;

        routes.forEach(([fromKey, toKey], routeIndex) => {
            const from = byKey.get(fromKey);
            const to = byKey.get(toKey);
            if (!from || !to) return;

            const startX = from.px;
            const startY = from.py;
            const endX = to.px;
            const endY = to.py;
            const midX = (startX + endX) / 2;
            const midY = (startY + endY) / 2;
            const dx = endX - startX;
            const dy = endY - startY;
            const distance = Math.hypot(dx, dy) || 1;
            let normalX = -dy / distance;
            let normalY = dx / distance;
            const radialX = midX - cx;
            const radialY = midY - cy;
            if (normalX * radialX + normalY * radialY < 0) {
                normalX *= -1;
                normalY *= -1;
            }
            const bend = Math.min(54, Math.max(34, distance * 0.17));
            const controlX = midX + normalX * bend;
            const controlY = midY + normalY * bend;

            // Keep each network link dotted, then send a visible packet along its curve.
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(startX, startY);
            ctx.quadraticCurveTo(controlX, controlY, endX, endY);
            ctx.strokeStyle = 'rgba(166, 181, 255, 0.32)';
            ctx.lineWidth = 1.35;
            ctx.lineCap = 'round';
            ctx.setLineDash([1, 9]);
            ctx.stroke();
            ctx.setLineDash([]);

            const phase = ((timestamp + routeIndex * cycleMs / routes.length) % cycleMs) / cycleMs;
            const progress = phase * cycleMs / activeMs;
            if (progress < 1) {
                const pointAt = t => ({
                    x: (1 - t) * (1 - t) * startX + 2 * (1 - t) * t * controlX + t * t * endX,
                    y: (1 - t) * (1 - t) * startY + 2 * (1 - t) * t * controlY + t * t * endY
                });
                const head = pointAt(progress);
                // A short trail of separate glowing dots makes direction and motion clear.
                [0.07, 0.035].forEach((offset, index) => {
                    const trailProgress = Math.max(0, progress - offset);
                    const trailPoint = pointAt(trailProgress);
                    ctx.beginPath();
                    ctx.arc(trailPoint.x, trailPoint.y, 1.3 + index * 0.35, 0, Math.PI * 2);
                    ctx.fillStyle = `rgba(150, 180, 255, ${0.22 + index * 0.18})`;
                    ctx.fill();
                });
                ctx.beginPath();
                ctx.arc(head.x, head.y, 3.2, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(200, 235, 255, 0.3)';
                ctx.shadowBlur = 7;
                ctx.shadowColor = 'rgba(120, 190, 255, 0.6)';
                ctx.fill();
                ctx.beginPath();
                ctx.arc(head.x, head.y, 2.3, 0, Math.PI * 2);
                ctx.fillStyle = 'rgba(235, 250, 255, 1)';
                ctx.fill();
            }
            ctx.restore();
        });
    }

    /* ---------- Draw planet ---------- */
    function drawPlanet(p) {
        const r  = Math.round(25 * p.scale);
        const ri = r - 2; // inner image radius
        const { px, py, alpha, border } = p;
        const img = IMGS[p.key];

        ctx.save();
        ctx.globalAlpha = alpha;

        /* Glow ring */
        ctx.beginPath();
        ctx.arc(px, py, r + 2.5, 0, Math.PI * 2);
        ctx.strokeStyle = border;
        ctx.lineWidth = 2 * p.scale;
        ctx.shadowBlur = 15 * p.scale;
        ctx.shadowColor = border;
        ctx.stroke();
        ctx.shadowBlur = 0;

        /* Background circle */
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        // Gemini has transparent bg → use dark; others have white bg → use white
        ctx.fillStyle = p.logoWhiteBg ? '#FFFFFF' : '#0D0820';
        ctx.fill();

        /* Image clipped to circle */
        if (img) {
            ctx.save();
            ctx.beginPath();
            ctx.arc(px, py, ri, 0, Math.PI * 2);
            ctx.clip();
            // Center-crop square from image
            const iw = img.naturalWidth  || img.width  || 100;
            const ih = img.naturalHeight || img.height || 100;
            const s  = Math.min(iw, ih);
            const sx = (iw - s) / 2;
            const sy = (ih - s) / 2;
            ctx.drawImage(img, sx, sy, s, s, px - ri, py - ri, ri * 2, ri * 2);
            ctx.restore();
        }

        /* Label */
        const fs = Math.round(12 * p.scale);
        ctx.font = `600 ${fs}px Inter, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = 'rgba(240,240,242,0.95)';
        ctx.shadowBlur = 6;
        ctx.shadowColor = 'rgba(0,0,0,0.8)';
        ctx.fillText(p.name, px, py + r + 6 * p.scale);
        ctx.shadowBlur = 0;

        /* Badge */
        const bfs = Math.round(9.5 * p.scale);
        ctx.font = `500 ${bfs}px Inter, sans-serif`;
        ctx.fillStyle = p.avail ? '#10A37F' : 'rgba(160,160,160,0.8)';
        ctx.fillText(p.avail ? '● Available' : '◌ Coming Soon', px, py + r + 6 * p.scale + fs + 3 * p.scale);

        ctx.restore();
    }

    /* ---------- Draw sun ---------- */
    function drawSun() {
        const r = 33;
        const img = IMGS.nexor;

        /* Radial glow halo */
        const grd = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 3);
        grd.addColorStop(0,   'rgba(160,154,248,0.35)');
        grd.addColorStop(0.4, 'rgba(108,99,255,0.12)');
        grd.addColorStop(1,   'rgba(0,0,0,0)');
        ctx.beginPath();
        ctx.arc(cx, cy, r * 3, 0, Math.PI * 2);
        ctx.fillStyle = grd;
        ctx.fill();

        /* Dark circle lets the inverted JPEG disappear into the page. */
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fillStyle = '#08080A';
        ctx.shadowBlur = 22;
        ctx.shadowColor = 'rgba(180,174,255,0.9)';
        ctx.fill();
        ctx.shadowBlur = 0;

        /* NexorSplash inside circle */
        if (img) {
            ctx.beginPath();
            ctx.arc(cx, cy, r - 1, 0, Math.PI * 2);
            ctx.clip();
            const iw = img.naturalWidth;
            const ih = img.naturalHeight;
            const s  = Math.min(iw, ih);
            const sx = (iw - s) / 2;
            const sy = (ih - s) / 2;
            ctx.drawImage(img, sx, sy, s, s, cx - r + 1, cy - r + 1, (r - 1) * 2, (r - 1) * 2);
        }
        ctx.restore();
    }
})();
