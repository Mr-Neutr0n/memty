(() => {
  const root = document.querySelector('[data-legacy-page="landing"] [data-session-demo]');
  if (!root || root.dataset.ready) return;
  root.dataset.ready = 'true';
  const prompt = root.querySelector('.demo-msg.user p');
  const answer = root.querySelector('.demo-msg.answer p');
  const composer = root.querySelector('.demo-composer');
  const memory = root.querySelector('.memory-event');
  const route = root.querySelector('.route-event');
  const model = route?.querySelector('strong');
  const tabs = [...document.querySelectorAll('.demo-scenes article')];
  const cursor = document.createElement('span');
  cursor.className = 'demo-cursor';
  cursor.setAttribute('aria-hidden', 'true');
  root.append(cursor);

  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const type = async (el, text, speed = 28) => {
    if (!el) return;
    el.textContent = '';
    for (const char of text) { el.textContent += char; await pause(speed); }
  };
  const scenes = [
    { prompt: 'Draft a concise follow-up for the launch project. Use my usual tone.', answer: 'Hi Maya — quick update: the launch assets are ready for review. Share any final notes when you have a moment, and I’ll fold them in before we send everything out.', model: 'Gemini Flash ↗', note: 'Launch project · concise updates · warm, direct tone' },
    { prompt: 'Review this Python function and explain why it is slow.', answer: 'The repeated lookup inside the loop is doing extra work. Build a lookup map once, then reuse it; that keeps the result clear and avoids scanning the list for every item.', model: 'Claude Haiku ↗', note: 'Code task · debugging · response quality checked by you' },
    { prompt: 'What did we decide about the launch timeline?', answer: 'The launch is planned for the second week of May. The latest project note says the final assets need review first, then the team can confirm the announcement date.', model: 'Gemini Flash ↗', note: 'Project timeline · latest discussion · launch notes' }
  ];
  let scene = 0;
  const play = async (index) => {
    scene = index % scenes.length;
    const item = scenes[scene];
    tabs.forEach((tab, i) => tab.classList.toggle('active', i === scene));
    if (composer) composer.innerHTML = 'Message NexorAI… <b>↑</b>';
    if (answer) answer.textContent = '';
    cursor.classList.add('moving');
    await pause(500);
    cursor.classList.remove('moving');
    await type(prompt, item.prompt, 25);
    await pause(450);
    if (memory) { memory.classList.add('is-active'); const note = memory.querySelector('small'); if (note) note.textContent = item.note; }
    await pause(800);
    if (model) model.textContent = item.model;
    if (route) route.classList.add('is-active');
    await pause(650);
    await type(answer, item.answer, 19);
    await pause(2800);
  };
  tabs.forEach((tab, i) => tab.addEventListener('click', () => { scene = i; play(scene); }));
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    tabs.forEach((tab, i) => tab.addEventListener('click', () => { const s = scenes[i]; prompt.textContent = s.prompt; answer.textContent = s.answer; model.textContent = s.model; }));
    return;
  }
  let stopped = false;
  const observer = new IntersectionObserver(entries => { stopped = !entries[0].isIntersecting; });
  observer.observe(root);
  (async function loop() { while (true) { if (!stopped) await play(scene++); else await pause(500); } })();
})();
