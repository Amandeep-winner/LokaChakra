"use client";

import React, { useEffect, useRef } from "react";
import cytoscape, { Core, EventObject } from "cytoscape";

interface GraphNodeData {
  id: string;
  label: string;
  type: string;
  tier?: number | null;
  trust_score?: number | null;
  current_org?: string | null;
  current_role?: string | null;
}

interface GraphEdgeData {
  id: string;
  source: string;
  target: string;
  label: string;
  confidence?: number;
  verified?: boolean;
}

interface NetworkCanvasProps {
  nodes: { data: GraphNodeData }[];
  edges: { data: GraphEdgeData }[];
  highlightedPathNodeIds: string[];
  highlightedPathEdgeIds: string[];
  onSelectNode: (nodeId: string) => void;
}

export default function NetworkCanvas({
  nodes,
  edges,
  highlightedPathNodeIds,
  highlightedPathEdgeIds,
  onSelectNode,
}: NetworkCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Initialize Cytoscape
    const cy = cytoscape({
      container: containerRef.current,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#64748b",
            label: "data(label)",
            color: "#e2e8f0",
            "font-size": "11px",
            "font-weight": "500",
            "text-valign": "bottom",
            "text-margin-y": 6,
            width: 32,
            height: 32,
            "border-width": 2,
            "border-color": "#1e293b",
            "transition-property": "background-color, border-color, opacity, width, height",
            "transition-duration": 0.25,
          },
        },
        // SELF_USER styling (Sky Blue)
        {
          selector: "node[label = 'SELF_USER'], node[id = 'SELF_USER']",
          style: {
            "background-color": "#38bdf8",
            "border-color": "#0284c7",
            "border-width": 3,
            width: 44,
            height: 44,
            "font-weight": "bold",
          },
        },
        // Tier 1 styling (Emerald)
        {
          selector: "node[type = 'Person'][tier = 1]",
          style: {
            "background-color": "#10b981",
            "border-color": "#059669",
            width: 36,
            height: 36,
          },
        },
        // Tier 2 styling (Amber)
        {
          selector: "node[type = 'Person'][tier = 2]",
          style: {
            "background-color": "#f59e0b",
            "border-color": "#d97706",
            width: 30,
            height: 30,
          },
        },
        // Tier 3 styling (Rose)
        {
          selector: "node[type = 'Person'][tier = 3]",
          style: {
            "background-color": "#f43f5e",
            "border-color": "#e11d48",
            width: 26,
            height: 26,
          },
        },
        // Organization styling (Slate Hexagon)
        {
          selector: "node[type = 'Organization']",
          style: {
            shape: "hexagon",
            "background-color": "#64748b",
            "border-color": "#475569",
            width: 38,
            height: 38,
          },
        },
        // Edge styling
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#334155",
            "target-arrow-color": "#334155",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            opacity: 0.75,
            label: "data(label)",
            "font-size": "9px",
            color: "#64748b",
            "text-rotation": "autorotate",
            "text-background-opacity": 0.8,
            "text-background-color": "#090d16",
            "text-background-padding": "2px",
          },
        },
        // Highlighted Path Nodes (Glowing Cyan)
        {
          selector: ".highlighted-node",
          style: {
            "border-color": "#06b6d4",
            "border-width": 4,
            "border-opacity": 1,
            opacity: 1,
            "shadow-blur": 15,
            "shadow-color": "#06b6d4",
            "shadow-opacity": 0.9,
          },
        },
        // Highlighted Path Edges (Glowing Cyan)
        {
          selector: ".highlighted-edge",
          style: {
            width: 4,
            "line-color": "#06b6d4",
            "target-arrow-color": "#06b6d4",
            opacity: 1,
            "shadow-blur": 12,
            "shadow-color": "#06b6d4",
            "shadow-opacity": 0.8,
            color: "#06b6d4",
          },
        },
        // Dimmed Non-Path Elements
        {
          selector: ".dimmed",
          style: {
            opacity: 0.25,
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        nodeRepulsion: () => 4500,
        idealEdgeLength: () => 90,
      },
    });

    cy.on("tap", "node", (evt: EventObject) => {
      const node = evt.target;
      onSelectNode(node.id());
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [onSelectNode]);

  // Update elements when nodes or edges prop change
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.batch(() => {
      cy.elements().remove();
      cy.add(nodes as any);
      cy.add(edges as any);

      const layout = cy.layout({
        name: "cose",
        animate: false,
        nodeRepulsion: () => 4500,
        idealEdgeLength: () => 90,
      });
      layout.run();
    });
  }, [nodes, edges]);

  // Handle path highlights
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.batch(() => {
      cy.elements().removeClass("highlighted-node highlighted-edge dimmed");

      if (highlightedPathNodeIds.length > 0) {
        // Dim all elements first
        cy.elements().addClass("dimmed");

        // Highlight matching path nodes
        for (const nodeId of highlightedPathNodeIds) {
          const node = cy.$id(nodeId);
          if (node.length > 0) {
            node.removeClass("dimmed").addClass("highlighted-node");
          }
        }

        // Highlight matching path edges
        for (const edgeId of highlightedPathEdgeIds) {
          const edge = cy.$id(edgeId);
          if (edge.length > 0) {
            edge.removeClass("dimmed").addClass("highlighted-edge");
          }
        }

        // Also connect adjacent path nodes if explicit edge IDs were not provided
        if (highlightedPathEdgeIds.length === 0) {
          for (let i = 0; i < highlightedPathNodeIds.length - 1; i++) {
            const u = highlightedPathNodeIds[i];
            const v = highlightedPathNodeIds[i + 1];
            cy.edges().forEach((edge) => {
              const src = edge.data("source");
              const tgt = edge.data("target");
              if ((src === u && tgt === v) || (src === v && tgt === u)) {
                edge.removeClass("dimmed").addClass("highlighted-edge");
              }
            });
          }
        }
      }
    });
  }, [highlightedPathNodeIds, highlightedPathEdgeIds]);

  return (
    <div className="relative w-full h-full bg-[#090d16]">
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
}
