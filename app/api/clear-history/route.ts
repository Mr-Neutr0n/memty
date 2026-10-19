import { NextResponse } from 'next/server';
import { clearConversationHistory } from '../../../gemini-service.js';

export const runtime = 'nodejs';

export async function POST() {
  try {
    clearConversationHistory('guest');
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Clear history error:', error);
    return NextResponse.json({ error: 'Failed to clear history' }, { status: 500 });
  }
}
