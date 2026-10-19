'use client';

import Link from 'next/link';
import { type FormEvent, useEffect, useState } from 'react';

type MemoryItem = { _id: string; fact: string; type: 'semantic' | 'style'; confidence: number; importance: number; pinned: boolean; status: 'active' | 'archived'; supersededBy?: string; sourceMessage: string; updatedAt: string; useCount: number };
type Usage = { model: string; requestCount: number; inputTokens: number; outputTokens: number; estimatedCostUsd: number; costTrackedRequests: number };
type Conversation = { conversationId: string; title: string; episodeSummary: string; messageCount: number; lastModel: string; updatedAt: string };

async function readJson(response: Response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.message || result.error || 'Request failed.');
  return result.data || {};
}

export default function MemoryDashboard() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [usage, setUsage] = useState<Usage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [archived, setArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState('');
  const [kind, setKind] = useState<'semantic' | 'style'>('semantic');

  async function refresh() {
    setLoading(true); setError('');
    try {
      const [memoryData, usageData, conversationData] = await Promise.all([
        fetch(`/backend/memory?archived=${archived}`, { cache: 'no-store' }).then(readJson),
        fetch('/backend/memory/usage', { cache: 'no-store' }).then(readJson),
        fetch('/backend/memory/conversations', { cache: 'no-store' }).then(readJson)
      ]);
      setMemories(memoryData.memories || []); setUsage(usageData.usage || []); setConversations(conversationData.conversations || []);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not load memory.'); }
    finally { setLoading(false); }
  }

  useEffect(() => { void refresh(); }, [archived]);

  async function update(id: string, changes: Partial<MemoryItem>) {
    try {
      await fetch(`/backend/memory/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(changes) }).then(readJson);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not update memory.'); }
  }

  async function remove(id: string) {
    if (!window.confirm('Permanently delete this memory?')) return;
    try { await fetch(`/backend/memory/${encodeURIComponent(id)}`, { method: 'DELETE' }).then(async response => { if (!response.ok) await readJson(response); }); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not delete memory.'); }
  }

  async function deleteConversations() {
    if (!window.confirm('Delete all saved conversations and summaries from NexorAI? Memories will stay.')) return;
    try {
      const response = await fetch('/backend/memory/conversations', { method: 'DELETE' });
      if (!response.ok) await readJson(response);
      localStorage.removeItem('nexorHistory');
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not delete conversations.'); }
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim()) return;
    try {
      await fetch('/backend/memory', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ fact: draft, type: kind }) }).then(readJson);
      setDraft(''); setArchived(false); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not add memory.'); }
  }

  const totalRequests = usage.reduce((sum, item) => sum + item.requestCount, 0);
  const totalTokens = usage.reduce((sum, item) => sum + item.inputTokens + item.outputTokens, 0);

  return <main className="memory-page">
    <header className="memory-header"><Link href="/" className="memory-brand">NexorAI</Link><nav><Link href="/chatbot">Workspace</Link><Link href="/memory" aria-current="page">Memory</Link><button onClick={() => { localStorage.removeItem('nexoraiUser'); void fetch('/users/logout', { method: 'POST' }).finally(() => { window.location.href = '/login'; }); }}>Sign out</button></nav></header>
    <div className="memory-main"><p className="memory-kicker">PORTABLE CONTEXT</p><h1>Your memory, across every model.</h1><p className="memory-lede">NexorAI keeps these facts independently of Gemini, Claude, and other providers. Review and remove anything you don't want used.</p>
      <div className="memory-stats"><div><span>Saved memories</span><strong>{memories.length}</strong></div><div><span>AI requests tracked</span><strong>{totalRequests}</strong></div><div><span>Tokens reported by providers</span><strong>{totalTokens.toLocaleString()}</strong></div></div>
      {error && <p className="memory-error" role="alert">{error} {error.includes('Sign in') || error.includes('session') ? <Link href="/login">Sign in</Link> : null}</p>}
      <section className="memory-panel"><div className="memory-panel-heading"><div><h2>Memory library</h2><p>Pin important context. Edit or delete anything at any time.</p></div><button className="memory-tab" onClick={() => setArchived(value => !value)}>{archived ? 'Show active' : 'Show archived'}</button></div>
        {!archived && <form className="memory-add" onSubmit={add}><input aria-label="Add a memory" value={draft} onChange={event => setDraft(event.target.value)} maxLength={500} placeholder="Add a fact or answer preference…"/><select aria-label="Memory type" value={kind} onChange={event => setKind(event.target.value as 'semantic' | 'style')}><option value="semantic">Fact</option><option value="style">Style</option></select><button type="submit">Add</button></form>}
        {loading ? <p className="memory-empty">Loading your memory…</p> : memories.length === 0 ? <p className="memory-empty">{archived ? 'No archived memories.' : 'No memories saved yet. Share a stable preference or project detail in chat, or add one above.'}</p> : <div className="memory-list">{memories.map(item => <article className="memory-card" key={item._id}><div className="memory-card-top"><span className={`memory-type ${item.type}`}>{item.type === 'style' ? 'Style' : 'Fact'}{item.pinned ? ' · Pinned' : ''}</span><span className="memory-meta">Confidence {Math.round(item.confidence * 100)}% · Used {item.useCount || 0} times · {new Date(item.updatedAt).toLocaleDateString()}</span></div><textarea aria-label="Memory fact" readOnly={archived} defaultValue={item.fact} maxLength={500} onBlur={event => { if (!archived && event.target.value.trim() !== item.fact) void update(item._id, { fact: event.target.value.trim() }); }}/>{archived && item.supersededBy && <p className="memory-source">Replaced by a newer memory.</p>}{item.sourceMessage && <p className="memory-source">Source: “{item.sourceMessage}”</p>}<div className="memory-actions">{!archived && <button onClick={() => void update(item._id, { pinned: !item.pinned })}>{item.pinned ? 'Unpin' : 'Pin memory'}</button>}<button className="danger" onClick={() => void remove(item._id)}>Delete</button></div></article>)}</div>}
      </section>
      <section className="memory-panel"><div className="memory-panel-heading"><div><h2>Recent conversations</h2><p>Short episode summaries help other models pick up the thread.</p></div><button className="memory-tab" onClick={() => void deleteConversations()}>Delete saved conversations</button></div>{conversations.length ? <div className="episode-list">{conversations.slice(0, 8).map(item => <article key={item.conversationId}><strong>{item.title || 'Conversation'}</strong><span>{item.episodeSummary || 'Summary will appear after a few turns.'}</span><small>{item.messageCount} messages · Last model: {item.lastModel || '—'}</small></article>)}</div> : <p className="memory-empty">Conversation summaries will appear here after chats are saved.</p>}</section>
      <section className="memory-panel"><div className="memory-panel-heading"><div><h2>Model usage</h2><p>Token counts come from provider reports. Cost is an estimate and appears only when rates are configured by the operator.</p></div></div>{usage.length ? <div className="usage-list">{usage.map(item => <div key={item.model}><strong>{item.model}</strong><span>{item.requestCount} requests · {(item.inputTokens + item.outputTokens).toLocaleString()} tokens</span><span>{item.costTrackedRequests ? `$${item.estimatedCostUsd.toFixed(4)} estimated` : 'Cost rates not configured'}</span></div>)}</div> : <p className="memory-empty">Usage will appear after your first model response.</p>}</section>
      <p className="memory-note">Memory is sent to the provider you choose with each request. Pinned facts are prioritized; deleting a memory removes it from future retrieval.</p>
    </div>
  </main>;
}
