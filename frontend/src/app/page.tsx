"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Search, ShieldAlert, Sparkles, Network, RefreshCw } from "lucide-react";
import NetworkCanvas from "@/components/NetworkCanvas";
import DossierDrawer, { PersonDossier } from "@/components/DossierDrawer";
import HitlQueueModal, { HITLEvidenceCard } from "@/components/HitlQueueModal";

interface PathStep {
  node_uid: string;
  node_name: string;
  node_type: string;
  reachability_tier?: number;
  trust_score?: number;
}

interface WarmPathResponse {
  target_query: string;
  total_cost: number;
  hop_count: number;
  steps: PathStep[];
  recommended_intro_script: string;
}

export default function LokachakraApp() {
  const [nodes, setNodes] = useState<any[]>([]);
  const [edges, setEdges] = useState<any[]>([]);
  const [tierMax, setTierMax] = useState<number>(3);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [dossier, setDossier] = useState<PersonDossier | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);

  // Search & Pathfinding
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [warmPath, setWarmPath] = useState<WarmPathResponse | null>(null);
  const [highlightedNodeIds, setHighlightedNodeIds] = useState<string[]>([]);
  const [isSearching, setIsSearching] = useState<boolean>(false);

  // HITL Queue
  const [pendingCards, setPendingCards] = useState<HITLEvidenceCard[]>([]);
  const [isHitlModalOpen, setIsHitlModalOpen] = useState<boolean>(false);

  const fetchGraphMap = useCallback(async (tier: number) => {
    try {
      const res = await fetch(`/api/v1/graph/map?tier_max=${tier}`);
      if (!res.ok) return;
      const data = await res.json();
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
    } catch (err) {
      console.error("Failed to load graph map", err);
    }
  }, []);

  const fetchPendingHitl = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/hitl/pending");
      if (!res.ok) return;
      const data = await res.json();
      setPendingCards(data || []);
    } catch (err) {
      console.error("Failed to load HITL queue", err);
    }
  }, []);

  useEffect(() => {
    fetchGraphMap(tierMax);
    fetchPendingHitl();
    const interval = setInterval(fetchPendingHitl, 30000);
    return () => clearInterval(interval);
  }, [fetchGraphMap, fetchPendingHitl, tierMax]);

  const handleSearchWarmPath = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setWarmPath(null);
      setHighlightedNodeIds([]);
      return;
    }

    setIsSearching(true);
    try {
      const res = await fetch(`/api/v1/graph/path?target=${encodeURIComponent(searchQuery.trim())}`);
      if (!res.ok) {
        setWarmPath(null);
        setHighlightedNodeIds([]);
        return;
      }
      const data: WarmPathResponse = await res.json();
      setWarmPath(data);

      if (data.steps && data.steps.length > 0) {
        // Collect node IDs from steps
        const stepUids = data.steps.map((s) => s.node_uid);
        setHighlightedNodeIds(stepUids);
      } else {
        setHighlightedNodeIds([]);
      }
    } catch (err) {
      console.error("Path search failed", err);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSelectNode = async (nodeId: string) => {
    setSelectedNodeId(nodeId);
    try {
      const res = await fetch(`/api/v1/graph/person/${encodeURIComponent(nodeId)}`);
      if (res.ok) {
        const data: PersonDossier = await res.json();
        setDossier(data);
        setIsDrawerOpen(true);
      }
    } catch (err) {
      console.error("Failed to fetch node dossier", err);
    }
  };

  const handleResolveHitl = async (cardId: string, threadId: string, action: "approve" | "reject") => {
    try {
      const res = await fetch("/api/v1/hitl/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ card_id: cardId, thread_id: threadId, action }),
      });
      if (res.ok) {
        setPendingCards((prev) => prev.filter((c) => c.card_id !== cardId));
        // Refresh graph map to reflect any new verified bridge
        fetchGraphMap(tierMax);
      }
    } catch (err) {
      console.error("Failed to resolve card", err);
    }
  };

  const clearPathHighlight = () => {
    setSearchQuery("");
    setWarmPath(null);
    setHighlightedNodeIds([]);
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden flex flex-col bg-[#090d16]">
      {/* Top Command Bar */}
      <header className="h-16 border-b border-slate-800/80 bg-[#0c1220]/90 backdrop-blur-md px-6 flex items-center justify-between z-30">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <Network className="w-6 h-6 text-cyan-400" />
            <h1 className="text-base font-bold tracking-tight text-white">
              Loka<span className="text-cyan-400">chakra</span>
            </h1>
          </div>

          {/* Search bar */}
          <form onSubmit={handleSearchWarmPath} className="relative w-80">
            <input
              type="text"
              placeholder="Find warmest path (e.g. Stripe, Rohan)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900/90 text-xs text-slate-100 pl-9 pr-8 py-2 rounded-lg border border-slate-700/80 focus:outline-none focus:border-cyan-500 placeholder-slate-500 transition"
            />
            <Search className="w-4 h-4 text-slate-400 absolute left-2.5 top-2.5" />
            {searchQuery && (
              <button
                type="button"
                onClick={clearPathHighlight}
                className="absolute right-2.5 top-2 text-xs text-slate-400 hover:text-white"
              >
                ×
              </button>
            )}
          </form>
        </div>

        {/* Legend & Controls */}
        <div className="flex items-center gap-6">
          <div className="hidden lg:flex items-center gap-4 text-xs text-slate-400">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#38bdf8]" />
              <span>Self</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#10b981]" />
              <span>Tier 1</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]" />
              <span>Tier 2</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#f43f5e]" />
              <span>Tier 3</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-[#64748b]" />
              <span>Org</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#06b6d4] shadow-[0_0_8px_#06b6d4]" />
              <span>Warm Path</span>
            </div>
          </div>

          {/* Tier Selector */}
          <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs">
            {[1, 2, 3].map((t) => (
              <button
                key={t}
                onClick={() => setTierMax(t)}
                className={`px-2.5 py-1 rounded font-medium transition ${
                  tierMax === t ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40" : "text-slate-400 hover:text-white"
                }`}
              >
                T{t}
              </button>
            ))}
          </div>

          {/* HITL Review Button */}
          <button
            onClick={() => setIsHitlModalOpen(true)}
            className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-200 transition"
          >
            <ShieldAlert className="w-4 h-4 text-amber-400" />
            <span>HITL Queue</span>
            {pendingCards.length > 0 && (
              <span className="ml-1 px-1.5 py-0.2 bg-amber-500 text-black font-bold rounded-full text-[10px]">
                {pendingCards.length}
              </span>
            )}
          </button>
        </div>
      </header>

      {/* Path Highlight Banner */}
      {warmPath && warmPath.steps && warmPath.steps.length > 0 && (
        <div className="absolute top-20 left-6 z-20 bg-slate-900/95 border border-cyan-500/50 rounded-xl p-4 shadow-2xl backdrop-blur-md max-w-lg space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-cyan-400 animate-pulse" />
              <span className="text-xs font-bold text-cyan-300 uppercase tracking-wider">
                Warmest Path Found
              </span>
            </div>
            <span className="text-xs text-slate-400">
              {warmPath.hop_count} hops · Cost: {warmPath.total_cost}
            </span>
          </div>

          <div className="text-xs font-medium text-slate-200 flex items-center flex-wrap gap-1">
            {warmPath.steps.map((step, i) => (
              <React.Fragment key={i}>
                <span className={i === 0 ? "text-sky-400" : i === warmPath.steps.length - 1 ? "text-cyan-400 font-bold" : "text-emerald-400"}>
                  {step.node_name}
                </span>
                {i < warmPath.steps.length - 1 && <span className="text-slate-600">→</span>}
              </React.Fragment>
            ))}
          </div>

          {warmPath.recommended_intro_script && (
            <p className="text-xs text-slate-300 italic bg-slate-950/80 p-2.5 rounded-lg border border-slate-800">
              "{warmPath.recommended_intro_script}"
            </p>
          )}
        </div>
      )}

      {/* Cytoscape Canvas */}
      <main className="flex-1 w-full h-full relative">
        <NetworkCanvas
          nodes={nodes}
          edges={edges}
          highlightedPathNodeIds={highlightedNodeIds}
          highlightedPathEdgeIds={[]}
          onSelectNode={handleSelectNode}
        />
      </main>

      {/* Slide-over Dossier Drawer */}
      <DossierDrawer
        dossier={dossier}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
      />

      {/* HITL Review Modal */}
      <HitlQueueModal
        isOpen={isHitlModalOpen}
        onClose={() => setIsHitlModalOpen(false)}
        cards={pendingCards}
        onResolve={handleResolveHitl}
      />
    </div>
  );
}
