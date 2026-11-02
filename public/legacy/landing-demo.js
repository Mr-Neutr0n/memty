(() => {
  const root = document.querySelector('[data-legacy-page="landing"] [data-session-demo]');
  if (!root || root.dataset.ready) return;
  root.dataset.ready = 'true';

  const title = root.querySelector('[data-demo-title]');
  const copy = root.querySelector('[data-demo-copy]');
  const code = root.querySelector('[data-demo-code]');
  const output = root.querySelector('[data-demo-output]');
  const tabs = [...document.querySelectorAll('.demo-scenes article')];
  const controls = document.createElement('div');
  controls.className = 'demo-controls';
  controls.innerHTML = '<div class="demo-control-actions"><button class="demo-control-button" type="button" data-demo-action="pause" aria-pressed="false">Pause</button><span class="demo-stage-status" aria-live="polite">Step 1 of 5</span></div>';
  root.after(controls);

  const pauseButton = controls.querySelector('[data-demo-action="pause"]');
  const status = controls.querySelector('.demo-stage-status');
  const steps = [
    {
      title: '1. Install Memty and the SDK',
      copy: 'Install the Memty Python package from the repository. It includes the model router and the local portable-memory vault.',
      code: 'python -m pip install "memty @ git+https://github.com/RohanNK86/memty.git@main"',
      output: ['Collecting memty from GitHub', 'Router, SDK, and Memty vault installed']
    },
    {
      title: '2. Configure providers and models',
      copy: 'Create the starter catalog, add model IDs and task tags, then provide API keys through environment variables.',
      code: 'memty init\n# Edit ~/.memty/models.json\n# Set provider API keys in your environment',
      output: ['Catalog: ~/.memty/models.json', 'Keep provider keys outside the model catalog']
    },
    {
      title: '3. Route from the user prompt',
      copy: 'Task rules inspect the prompt, then rank eligible configured models using task tags and catalog settings.',
      code: 'from memty import load_client\nclient = load_client()\nresult = client.route(\n    "Review this Python function",\n    strategy="rules",\n)\nprint(result.task_type, result.model_id)',
      output: ['task=code | selected=<eligible configured model ID>', 'Rules prefer code tags, then capability, price, and latency', 'Route preview is local; no model request is sent']
    },
    {
      title: '4. Retrieve and pass relevant memory',
      copy: 'Save an explicit fact. On chat, Memty retrieves relevant facts allowed for the selected provider and adds them to that model request.',
      code: 'client = load_client()\nclient.remember("work.preferences", "editor", "VS Code")\nreply = client.chat(\n    "Which editor do I use?",\n    chat_id="editor-chat",\n    strategy="rules",\n)',
      output: ['Memty retrieves matching provider-allowed facts', 'Selected model receives the prompt with relevant saved context', 'Chat transcript remains separate from the durable fact vault']
    },
    {
      title: '5. Switch models, keep saved memory',
      copy: 'Pin a different configured model to another chat. The SDK uses the same local fact vault; chat transcripts stay separate.',
      code: 'client.select_model("YOUR_MODEL_ID", chat_id="second-chat")\nreply = client.chat(\n    "Which editor do I use?",\n    chat_id="second-chat",\n)\nprint(reply.text)',
      output: ['Replace YOUR_MODEL_ID with an ID from your catalog', 'Relevant eligible memory can be recalled by the second model']
    }
  ];

  let runId = 0;
  let paused = false;
  let visible = true;
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const wait = async (ms, id) => {
    let remaining = ms;
    while (remaining > 0 && id === runId) {
      if (paused || !visible) { await delay(100); continue; }
      const slice = Math.min(50, remaining);
      await delay(slice);
      remaining -= slice;
    }
    return id === runId;
  };

  const typeCode = async (value, id) => {
    if (!code) return;
    code.textContent = '';
    for (const character of value) {
      if (!(await wait(28, id))) return;
      code.textContent += character;
    }
  };

  const play = async (index = 0) => {
    const id = ++runId;
    const stepIndex = (index + steps.length) % steps.length;
    const step = steps[stepIndex];
    tabs.forEach((tab, i) => {
      tab.classList.toggle('active', i === stepIndex);
      tab.setAttribute('aria-selected', String(i === stepIndex));
    });
    if (title) title.textContent = step.title;
    if (copy) copy.textContent = step.copy;
    if (output) output.replaceChildren();
    if (code) code.textContent = '';
    if (status) status.textContent = `Step ${stepIndex + 1} of ${steps.length} - Writing example`;

    if (!(await wait(700, id))) return;
    await typeCode(step.code, id);
    if (id !== runId) return;
    if (status) status.textContent = `Step ${stepIndex + 1} of ${steps.length} - Running example`;
    for (const line of step.output) {
      if (!(await wait(700, id))) return;
      const row = document.createElement('div');
      row.className = 'demo-output-line';
      row.textContent = line;
      if (output) output.append(row);
    }
    if (status) status.textContent = `Step ${stepIndex + 1} of ${steps.length} - Complete`;
    if (await wait(3200, id)) void play(stepIndex + 1);
  };

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const selectStep = index => {
    if (!reducedMotion) {
      paused = false;
      if (pauseButton) { pauseButton.textContent = 'Pause'; pauseButton.setAttribute('aria-pressed', 'false'); }
      void play(index);
      return;
    }
    const step = steps[index];
    ++runId;
    tabs.forEach((tab, i) => { tab.classList.toggle('active', i === index); tab.setAttribute('aria-selected', String(i === index)); });
    if (title) title.textContent = step.title;
    if (copy) copy.textContent = step.copy;
    if (code) code.textContent = step.code;
    if (output) output.replaceChildren(...step.output.map(line => {
      const row = document.createElement('div');
      row.className = 'demo-output-line';
      row.textContent = line;
      return row;
    }));
    if (status) status.textContent = `Step ${index + 1} of ${steps.length} - Complete`;
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectStep(index));
    tab.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectStep(index); }
    });
  });
  const replayButton = root.querySelector('[data-demo-action="replay"]');
  if (replayButton) replayButton.addEventListener('click', () => selectStep(0));
  if (pauseButton) pauseButton.addEventListener('click', () => {
    paused = !paused;
    pauseButton.textContent = paused ? 'Resume' : 'Pause';
    pauseButton.setAttribute('aria-pressed', String(paused));
  });
  const observer = new IntersectionObserver(entries => { visible = entries[0] ? entries[0].isIntersecting : true; });
  observer.observe(root);
  if (reducedMotion) selectStep(0);
  else void play(0);
})();
