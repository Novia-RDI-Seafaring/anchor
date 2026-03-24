'use client';
import React, { useState } from 'react';
import { useCopilotChatInternal } from '@copilotkit/react-core';
import { aguiToGQL } from '@copilotkit/runtime-client-gql';
import { ChevronDown, ChevronRight, Wrench, CheckCircle2, AlertCircle, MessageSquare } from 'lucide-react';

interface ToolCall {
  id: string;
  name: string;
  args: unknown;
  result?: unknown;
  resultId?: string;
}

interface Run {
  userMessage: string;
  toolCalls: ToolCall[];
}

function tryParse(raw: unknown): unknown {
  if (typeof raw !== 'string') return raw;
  try { return JSON.parse(raw); } catch { return raw; }
}

function JsonBlock({ value }: { value: unknown }) {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return (
    <pre className="mt-1 rounded bg-neutral-100 dark:bg-neutral-800 p-2 text-[11px] leading-relaxed overflow-x-auto whitespace-pre-wrap break-words text-neutral-700 dark:text-neutral-300 max-h-64">
      {text}
    </pre>
  );
}

function ToolCallRow({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const hasResult = call.result !== undefined;

  return (
    <div className="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800/60 transition-colors"
      >
        {open ? <ChevronDown size={13} className="shrink-0 text-neutral-400" /> : <ChevronRight size={13} className="shrink-0 text-neutral-400" />}
        <Wrench size={13} className="shrink-0 text-amber-500" />
        <span className="font-mono text-xs font-semibold text-neutral-800 dark:text-neutral-200 flex-1 truncate">
          {call.name}
        </span>
        {hasResult
          ? <CheckCircle2 size={13} className="shrink-0 text-emerald-500" />
          : <AlertCircle size={13} className="shrink-0 text-neutral-300 dark:text-neutral-600" />
        }
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2 border-t border-neutral-100 dark:border-neutral-800 pt-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 mb-0.5">Arguments</p>
            <JsonBlock value={call.args} />
          </div>
          {hasResult && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 mb-0.5">Result</p>
              <JsonBlock value={call.result} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RunBlock({ run, index, defaultOpen }: { run: Run; index: number; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left bg-neutral-50 dark:bg-neutral-800/40 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
      >
        {open ? <ChevronDown size={13} className="shrink-0 text-neutral-400" /> : <ChevronRight size={13} className="shrink-0 text-neutral-400" />}
        <MessageSquare size={13} className="shrink-0 text-blue-500" />
        <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300 flex-1 truncate">
          {run.userMessage || `Run ${index + 1}`}
        </span>
        <span className="text-[10px] text-neutral-400 shrink-0">
          {run.toolCalls.length} tool{run.toolCalls.length !== 1 ? 's' : ''}
        </span>
      </button>

      {open && run.toolCalls.length > 0 && (
        <div className="px-3 pb-3 pt-2 space-y-1.5">
          {run.toolCalls.map(call => (
            <ToolCallRow key={call.id} call={call} />
          ))}
        </div>
      )}

      {open && run.toolCalls.length === 0 && (
        <p className="px-3 py-2 text-xs text-neutral-400">No tool calls in this run.</p>
      )}
    </div>
  );
}

export function RunsPanel({ onClose }: { onClose: () => void }) {
  const { messages = [] } = useCopilotChatInternal();

  // Build runs: group tool calls by the preceding user message
  const runs: Run[] = [];
  let currentRun: Run | null = null;
  const pendingCalls: Map<string, ToolCall> = new Map();

  for (const msg of messages) {
    const legacy: any = aguiToGQL(msg as any)[0];
    if (!legacy) continue;

    if (legacy.role === 'user' || legacy.isHumanMessage?.()) {
      const text = typeof legacy.content === 'string'
        ? legacy.content
        : legacy.content?.[0]?.text ?? '';
      currentRun = { userMessage: text, toolCalls: [] };
      runs.push(currentRun);
    } else if (legacy.isActionExecutionMessage?.()) {
      const call: ToolCall = {
        id: legacy.id ?? Math.random().toString(),
        name: legacy.name ?? 'unknown',
        args: tryParse(legacy.arguments),
      };
      pendingCalls.set(call.id, call);
      if (currentRun) {
        currentRun.toolCalls.push(call);
      } else {
        // Tool calls before first user message
        currentRun = { userMessage: '(agent init)', toolCalls: [call] };
        runs.push(currentRun);
      }
    } else if (legacy.isResultMessage?.()) {
      const execId = legacy.actionExecutionId;
      if (execId && pendingCalls.has(execId)) {
        const call = pendingCalls.get(execId)!;
        call.result = tryParse(legacy.result);
      }
    }
  }

  if (runs.length === 0) {
    return (
      <div className="absolute inset-0 z-10 bg-white/96 dark:bg-neutral-950/96 backdrop-blur-sm flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Runs</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500"><span className="sr-only">Close</span>✕</button>
        </div>
        <div className="flex-1 flex items-center justify-center text-sm text-neutral-400">No agent runs yet.</div>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 z-10 bg-white/96 dark:bg-neutral-950/96 backdrop-blur-sm flex flex-col">
      <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800 shrink-0">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Runs</h2>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500">✕</button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {runs.map((run, i) => (
          <RunBlock key={i} run={run} index={i} defaultOpen={i === runs.length - 1} />
        ))}
      </div>
    </div>
  );
}
