"use client";

import React, { useState } from "react";
import { X, CheckCircle2, XCircle, AlertCircle, ExternalLink } from "lucide-react";

export interface HITLEvidenceCard {
  card_id: string;
  langgraph_thread_id: string;
  action_type: string;
  subject_a_name: string;
  subject_b_name: string;
  proposed_relation: string;
  confidence_score: number;
  evidence_summary: string;
  source_urls: string[];
  status: string;
  created_at: string;
}

interface HitlQueueModalProps {
  isOpen: boolean;
  onClose: () => void;
  cards: HITLEvidenceCard[];
  onResolve: (cardId: string, threadId: string, action: "approve" | "reject") => Promise<void>;
}

export default function HitlQueueModal({
  isOpen,
  onClose,
  cards,
  onResolve,
}: HitlQueueModalProps) {
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleAction = async (card: HITLEvidenceCard, action: "approve" | "reject") => {
    setResolvingId(card.card_id);
    try {
      await onResolve(card.card_id, card.langgraph_thread_id, action);
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-[#111827] border border-slate-800 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <AlertCircle className="w-5 h-5 text-amber-400" />
            <h2 className="text-lg font-bold text-slate-100">
              Human-in-the-Loop Review Queue ({cards.length})
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {cards.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-500/50 mb-2" />
              <p className="text-sm font-medium">All clear! No pending verification hypotheses.</p>
            </div>
          ) : (
            cards.map((card) => (
              <div
                key={card.card_id}
                className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-3"
              >
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-slate-200">
                    {card.subject_a_name}{" "}
                    <span className="text-cyan-400 font-normal">
                      -[{card.proposed_relation}]-&gt;
                    </span>{" "}
                    {card.subject_b_name}
                  </div>
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-800 font-mono">
                    {(card.confidence_score * 100).toFixed(0)}% conf
                  </span>
                </div>

                <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/50 p-2.5 rounded-lg border border-slate-800/60">
                  {card.evidence_summary}
                </p>

                {card.source_urls && card.source_urls.length > 0 && (
                  <div className="flex items-center gap-2 text-[11px] text-slate-400">
                    <span>Sources:</span>
                    {card.source_urls.map((url, idx) => (
                      <a
                        key={idx}
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cyan-400 hover:underline flex items-center gap-0.5"
                      >
                        [Link {idx + 1}] <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    ))}
                  </div>
                )}

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800/60">
                  <button
                    disabled={resolvingId === card.card_id}
                    onClick={() => handleAction(card, "reject")}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-rose-400 bg-rose-950/40 border border-rose-900 hover:bg-rose-900/50 transition disabled:opacity-50"
                  >
                    <XCircle className="w-3.5 h-3.5" /> Reject Match
                  </button>
                  <button
                    disabled={resolvingId === card.card_id}
                    onClick={() => handleAction(card, "approve")}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-emerald-400 bg-emerald-950/40 border border-emerald-900 hover:bg-emerald-900/50 transition disabled:opacity-50"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" /> Confirm & Lock
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
