// Memty GitHub Pages: mobile navigation, active-section highlighting, copy buttons.
const menuButton = document.querySelector('.menu-button');
const sidebar = document.querySelector('.sidebar');

function setMenu(open) {
  sidebar.classList.toggle('open', open);
  menuButton?.setAttribute('aria-expanded', String(open));
}

menuButton?.addEventListener('click', () => setMenu(!sidebar.classList.contains('open')));
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') setMenu(false); });
document.querySelectorAll('.sidebar a').forEach((link) => link.addEventListener('click', () => setMenu(false)));

// Highlight the section currently in view.
const links = [...document.querySelectorAll('.nav-link')];
const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (!entry.isIntersecting) return;
    links.forEach((link) => link.classList.toggle('active', link.getAttribute('href') === `#${entry.target.id}`));
  });
}, { rootMargin: '-30% 0px -60% 0px' });
document.querySelectorAll('.section-anchor').forEach((section) => observer.observe(section));

// Copy buttons, with a fallback for browsers that block the async clipboard API.
document.querySelectorAll('.copy-button').forEach((button) => {
  button.addEventListener('click', async () => {
    const text = button.dataset.copy || '';
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = Object.assign(document.createElement('textarea'), { value: text });
      area.style.cssText = 'position:fixed;opacity:0';
      document.body.append(area);
      area.select();
      document.execCommand('copy');
      area.remove();
    }
    const original = button.textContent;
    button.textContent = 'Copied';
    setTimeout(() => { button.textContent = original; }, 1400);
  });
});
