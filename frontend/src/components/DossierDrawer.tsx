"use client";

import React, { useState } from "react";
import { X, Copy, Check, Briefcase, Link2, Shield, Calendar, Quote } from "lucide-react";

export interface CareerHistoryItem {
  organization: string;
  role?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  is_active: boolean;
  evidence_snippet?: string | null;
}

export interface PersonConnectionItem {
  target_name: string;
  target_uid?: string | null;
  target_type: string;
  relation: string;
  confidence_score: number;
  verified: boolean;
}

export interface PersonDossier {
  uid: string;
  full_name: string;
  reachability_tier?: number | null;
  trust_score: number;
  current_org?: string | null;
  current_role?: string | null;
  email?: string | null;
  phone?: string | null;
  career_history: CareerHistoryItem[];
  connections: PersonConnectionItem[];
  evidence_snippets: string[];
  recommended_intro?: string | null;
}

interface DossierDrawerProps {
  dossier: PersonDossier | null;
  isOpen: boolean;
  onClose: () => void;
}

export default function DossierDrawer({ dossier, isOpen, onClose }: DossierDrawerProps) {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !dossier) return null;

  const handleCopyIntro = () => {
    if (dossier.recommended_intro) {
      navigator.clipboard.writeText(dossier.recommended_intro);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const trustPercent = Math.min(100, Math.max(0, dossier.trust_score));
  const getTrustColor = (score: number) => {
    if (score >= 80) return "text-emerald-400";
    if (score >= 55) return "text-amber-400";
    return "text-rose-400";
  };

  return (
    <div className="fixed inset-y-0 right-0 w-96 max-w-full bg-[#111827] border-l border-slate-800 shadow-2xl z-50 flex flex-col transition-transform duration-300">
      {/* Header */}
      <div className="p-5 border-b border-slate-800 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-slate-100">{dossier.full_name}</h2>
            {dossier.reachability_tier && (
              <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${
                dossier.reachability_tier === 1 ? "bg-emerald-950 text-emerald-400 border border-emerald-800" :
                dossier.reachability_tier === 2 ? "bg-amber-950 text-amber-400 border border-amber-800" :
                "bg-rose-950 text-rose-400 border border-rose-800"
              }`}>
                Tier {dossier.reachability_tier}
              </span>
            )}
          </div>
          {(dossier.current_role || dossier.current_org) && (
            <p className="text-sm text-slate-400 mt-1">
              {dossier.current_role} {dossier.current_role && dossier.current_org ? "at" : ""} {dossier.current_org}
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-md transition"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {/* Trust Score Gauge */}
        <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5" /> Trust Score
            </span>
            <span className={`text-lg font-bold ${getTrustColor(dossier.trust_score)}`}>
              {dossier.trust_score.toFixed(1)} / 100
            </span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                dossier.trust_score >= 80 ? "bg-emerald-500" :
                dossier.trust_score >= 55 ? "bg-amber-500" : "bg-rose-500"
              }`}
              style={{ width: `${trustPercent}%` }}
            />
          </div>
        </div>

        {/* Actionable Warm Intro Script */}
        {dossier.recommended_intro && (
          <div className="bg-slate-900/80 p-4 rounded-xl border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-cyan-400">
                Warm Intro Message
              </span>
              <button
                onClick={handleCopyIntro}
                className="flex items-center gap-1 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 px-2 py-1 rounded transition"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="text-xs text-slate-300 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 italic leading-relaxed">
              "{dossier.recommended_intro}"
            </p>
          </div>
        )}

        {/* Temporal Career History */}
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
            <Briefcase className="w-3.5 h-3.5" /> Temporal Career History
          </h3>
          {dossier.career_history.length === 0 ? (
            <p className="text-xs text-slate-500">No career history recorded yet.</p>
          ) : (
            <div className="space-y-2.5">
              {dossier.career_history.map((item, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-slate-900/60 rounded-lg border border-slate-800/80 space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-200">
                      {item.organization}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                      item.is_active
                        ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800"
                        : "bg-slate-800 text-slate-400"
                    }`}>
                      {item.is_active ? "Active" : "Past"}
                    </span>
                  </div>
                  {item.role && <p className="text-xs text-slate-400">{item.role}</p>}
                  {(item.valid_from || item.valid_to) && (
                    <div className="text-[11px] text-slate-500 flex items-center gap-1 pt-1">
                      <Calendar className="w-3 h-3" />
                      <span>{item.valid_from || "Unknown"} → {item.valid_to || "Present"}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Verbatim Audio Provenance Quotes */}
        {dossier.evidence_snippets && dossier.evidence_snippets.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
              <Quote className="w-3.5 h-3.5" /> Verbatim Provenance Quotes
            </h3>
            <div className="space-y-2">
              {dossier.evidence_snippets.map((snip, idx) => (
                <div
                  key={idx}
                  className="text-xs text-slate-300 bg-slate-900/40 border-l-2 border-cyan-500 pl-3 py-1.5 italic"
                >
                  "{snip}"
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Network Connections */}
        {dossier.connections && dossier.connections.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
              <Link2 className="w-3.5 h-3.5" /> Connections ({dossier.connections.length})
            </h3>
            <div className="space-y-2">
              {dossier.connections.map((conn, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-2.5 bg-slate-900/50 rounded-lg border border-slate-800 text-xs"
                >
                  <div>
                    <span className="font-medium text-slate-200">{conn.target_name}</span>
                    <span className="text-slate-500 ml-1.5">({conn.relation})</span>
                  </div>
                  <span className="text-slate-400 text-[11px]">
                    {(conn.confidence_score * 100).toFixed(0)}% conf
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
