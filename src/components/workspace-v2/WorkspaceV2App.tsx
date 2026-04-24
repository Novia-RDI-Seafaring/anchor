"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CopilotKit } from "@copilotkit/react-core";
import { useCoAgent, useCopilotChatInternal } from "@copilotkit/react-core";
import { aguiToGQL } from "@copilotkit/runtime-client-gql";
import { useSession } from "next-auth/react";
import {
  Activity,
  ArrowUp,
  Check,
  ChevronDown,
  Cpu,
  Database,
  FileText,
  GripVertical,
  Layers,
  Loader2,
  MessageSquare,
  Network,
  PanelRight,
  Paperclip,
  Pencil,
  Plus,
  StopCircle,
  X,
} from "lucide-react";

import { ConversationRestorer } from "@/components/chat/ConversationRestorer";
import { CanvasGraph } from "@/components/canvas/CanvasGraph";
import { PDFModal, type PDFHighlight } from "@/components/canvas/PDFModal";
import { ResourcePalette, type PaletteTab } from "@/components/canvas/ResourcePalette";
import { AgSelect } from "@/components/ui/AgComponents";
import { useApp } from "@/contexts/AppContext";
import { API_URL } from "@/lib/api-config";
import { toPersistableChatMessages } from "@/lib/chat-history";
import { normalizeModelOptions } from "@/lib/models";
import type { ModelOption } from "@/types";
import {
  buildCanvasStatePayload,
  buildEvidenceImageUrl,
  createCanvasTab,
  createDefaultCanvasTab,
  makeDocumentCanvasNode,
  mergeActiveCanvasTab,
  normalizeSavedCanvasState,
  searchGoldForParams,
  type CanvasState,
  type CanvasTab,
  type FlowPosition,
} from "@/components/layout/mainContentUtils";

type PipelineDetail = {
  filename: string;
  slug: string;
  bronze?: { path?: string; size_kb?: number } | null;
  silver?: {
    page_count?: number;
    outline_count?: number;
    table_count?: number;
    figure_count?: number;
    pages?: Array<{ page: number; has_png?: boolean; has_md?: boolean; has_raw_md?: boolean }>;
  } | null;
  gold?: {
    pages?: Array<{ page: number; region_count: number; region_kinds?: string[] }>;
  } | null;
  status?: { stage: string; current: number; total: number };
};

type UploadingFile = {
  file: File;
  status: "uploading" | "success" | "error";
  error?: string;
};

type Controller = ReturnType<typeof useWorkspaceV2Controller>;

function useWorkspaceV2Controller() {
  const { messages: visibleMessages = [] } = useCopilotChatInternal();
  const {
    activeConversationId,
    updateConversation,
    conversations,
    loadConversationMessages,
    activeDocumentId,
    documents,
    focusedChatNodes,
    clearFocusedChatNodes,
  } = useApp();
  const { data: session } = useSession();
  const userId = (session?.user as any)?.id ?? "local-dev-user";
  const userHeaders = { "x-user-id": userId };

  const { state, setState } = useCoAgent({
    name: "my_agent",
    initialState: {
      nodes: [],
      relations: [],
      active_document_id: null as string | null,
      focused_chat_nodes: [],
    } as CanvasState,
  });

  const canvas = state as any;

  const [canvasTabs, setCanvasTabs] = useState<CanvasTab[]>([createDefaultCanvasTab()]);
  const [activeCanvasId, setActiveCanvasId] = useState<string>("default");
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});

  const positionsRef = useRef(positions);
  useEffect(() => {
    positionsRef.current = positions;
  }, [positions]);

  const canvasTabsRef = useRef(canvasTabs);
  useEffect(() => {
    canvasTabsRef.current = canvasTabs;
  }, [canvasTabs]);

  const activeCanvasIdRef = useRef(activeCanvasId);
  useEffect(() => {
    activeCanvasIdRef.current = activeCanvasId;
  }, [activeCanvasId]);

  useEffect(() => {
    setState((prev: any) => {
      const nextActiveDocumentId = activeDocumentId ?? null;
      if (prev?.active_document_id === nextActiveDocumentId) return prev;
      return { ...prev, active_document_id: nextActiveDocumentId };
    });
    // setState from useCoAgent is not referentially stable; depending on it creates an update loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDocumentId]);

  useEffect(() => {
    const nextFocusedChatNodes = focusedChatNodes.map((node) => ({
        node_id: node.nodeId,
        node_type: node.nodeType,
        title: node.title,
        summary: node.summary,
        filename: node.filename,
        page: node.page,
        bbox: node.bbox ?? [],
      }));

    setState((prev: any) => {
      const previous = JSON.stringify(prev?.focused_chat_nodes ?? []);
      const next = JSON.stringify(nextFocusedChatNodes);
      if (previous === next) return prev;
      return {
        ...prev,
        focused_chat_nodes: nextFocusedChatNodes,
      };
    });
    // setState from useCoAgent is not referentially stable; depending on it creates an update loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedChatNodes]);

  const prevConversationId = useRef<string | null>(null);
  useEffect(() => {
    if (!activeConversationId || activeConversationId === prevConversationId.current) return;
    prevConversationId.current = activeConversationId;

    loadConversationMessages(activeConversationId).then(({ canvas_state }) => {
      const restored = normalizeSavedCanvasState(canvas_state, documents);
      clearFocusedChatNodes();
      setCanvasTabs(restored.tabs);
      setActiveCanvasId(restored.activeTabId);
      setPositions(restored.positions);
      setState((prev: any) => ({
        ...prev,
        nodes: restored.nodes,
        relations: restored.relations,
        workspace_doc_ids:
          restored.workspaceDocIds.length > 0 ? restored.workspaceDocIds : prev.workspace_doc_ids,
        active_document_id: activeDocumentId ?? prev.active_document_id ?? null,
        focused_chat_nodes: [],
      }));
    });
    // setState from useCoAgent is not referentially stable; do not include it here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    activeConversationId,
    activeDocumentId,
    clearFocusedChatNodes,
    documents,
    loadConversationMessages,
  ]);

  const canvasSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!activeConversationId) return;
    if (canvasSaveTimer.current) clearTimeout(canvasSaveTimer.current);
    canvasSaveTimer.current = setTimeout(() => {
      const payload = buildCanvasStatePayload(
        canvasTabsRef.current,
        activeCanvasIdRef.current,
        canvas?.nodes ?? [],
        canvas?.relations ?? [],
        positionsRef.current,
        canvas?.workspace_doc_ids ?? [],
      );
      updateConversation(activeConversationId, { canvas_state: payload } as any);
    }, 1000);
    return () => {
      if (canvasSaveTimer.current) clearTimeout(canvasSaveTimer.current);
    };
  }, [canvas, activeConversationId, updateConversation]);

  const switchCanvasTab = useCallback(
    (newId: string) => {
      if (newId === activeCanvasIdRef.current) return;

      setCanvasTabs((prev) =>
        mergeActiveCanvasTab(
          prev,
          activeCanvasIdRef.current,
          (canvas as any)?.nodes ?? [],
          (canvas as any)?.relations ?? [],
          positionsRef.current,
        ),
      );

      const newTab = canvasTabsRef.current.find((tab) => tab.id === newId);
      if (newTab) {
        setState((prev: any) => ({ ...prev, nodes: newTab.nodes, relations: newTab.relations }));
        setPositions(newTab.positions);
      }
      setActiveCanvasId(newId);
    },
    [canvas, setState],
  );

  const addCanvasTab = useCallback(() => {
    setCanvasTabs((prev) => {
      const saved = mergeActiveCanvasTab(
        prev,
        activeCanvasIdRef.current,
        (canvas as any)?.nodes ?? [],
        (canvas as any)?.relations ?? [],
        positionsRef.current,
      );
      const newTab = createCanvasTab(saved.length + 1);
      setTimeout(() => {
        setState((prevState: any) => ({ ...prevState, nodes: [], relations: [] }));
        setPositions({});
        setActiveCanvasId(newTab.id);
      }, 0);
      return [...saved, newTab];
    });
  }, [canvas, setState]);

  const closeCanvasTab = useCallback(
    (id: string) => {
      setCanvasTabs((prev) => {
        if (prev.length <= 1) return prev;
        const next = prev.filter((tab) => tab.id !== id);
        if (id === activeCanvasIdRef.current) {
          const newActive = next[next.length - 1] ?? next[0];
          if (newActive) {
            setState((p: any) => ({ ...p, nodes: newActive.nodes, relations: newActive.relations }));
            setPositions(newActive.positions);
            setActiveCanvasId(newActive.id);
          }
        }
        return next;
      });
    },
    [setState],
  );

  const posSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const persistPositions = useCallback(
    (updated: Record<string, { x: number; y: number }>) => {
      positionsRef.current = updated;
      setPositions(updated);
      if (!activeConversationId) return;
      if (posSaveTimer.current) clearTimeout(posSaveTimer.current);
      posSaveTimer.current = setTimeout(() => {
        const payload = buildCanvasStatePayload(
          canvasTabsRef.current,
          activeCanvasIdRef.current,
          canvas?.nodes ?? [],
          canvas?.relations ?? [],
          updated,
          canvas?.workspace_doc_ids ?? [],
        );
        updateConversation(activeConversationId, { canvas_state: payload } as any);
      }, 500);
    },
    [activeConversationId, canvas, updateConversation],
  );

  const handlePositionsChange = useCallback(
    (updated: Record<string, { x: number; y: number }>) => {
      persistPositions(updated);
    },
    [persistPositions],
  );

  const handleSaveSelection = useCallback(
    async (selectedNodeIds: string[], name?: string) => {
      const allNodes: any[] = canvas?.nodes ?? [];
      const allRels: any[] = canvas?.relations ?? [];
      const nodeSet = new Set(selectedNodeIds);
      const nodes = allNodes
        .filter((node) => nodeSet.has(node.id))
        .map((node) => ({
          ...node,
          position: positionsRef.current[node.id] ?? null,
        }));
      const relations = allRels.filter((rel) => nodeSet.has(rel.from_id) && nodeSet.has(rel.to_id));
      const snippetName = name || (nodes[0]?.title || nodes[0]?.text || "Snippet").slice(0, 40);
      const res = await fetch(`${API_URL}/api/snippets`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...userHeaders },
        body: JSON.stringify({ id: crypto.randomUUID(), name: snippetName, nodes, relations }),
      }).catch(() => null);
      if (!res?.ok) console.error("[snippets] Save failed:", res?.status, res?.statusText);
    },
    [canvas, userHeaders],
  );

  const handleSimulateComplete = useCallback(
    (
      fmuNodeId: string,
      jobId: string,
      filename: string,
      signalNames: string[],
      paramValues: Record<string, string>,
      stopTime: number,
    ) => {
      const numericParams: Record<string, number> = {};
      Object.entries(paramValues).forEach(([key, value]) => {
        const parsed = parseFloat(value);
        if (!Number.isNaN(parsed)) numericParams[key] = parsed;
      });
      const plotNode = {
        id: `plot_${Date.now()}`,
        node_type: "plot",
        status: "found",
        title: `${filename} - simulation`,
        plot_job_id: jobId,
        plot_fmu_filename: filename,
        plot_signal_names: signalNames,
        plot_stop_time: stopTime,
        plot_param_values: numericParams,
        last_updated_run_id: "",
        text: "",
        spec_title: "",
        properties: [],
        fmu_filename: "",
        fmu_model_name: "",
        fmu_variables: [],
        fmu_param_values: {},
        filename: "",
        page: 0,
        bbox: [],
        highlights: [],
      };
      const relation = {
        from_id: fmuNodeId,
        to_id: plotNode.id,
        label: Object.entries(numericParams)
          .map(([key, value]) => `${key}=${value}`)
          .join(", ") || "simulate",
      };
      const currentCanvas = canvas as any;
      setState({
        ...currentCanvas,
        nodes: [...(currentCanvas?.nodes ?? []), plotNode],
        relations: [...(currentCanvas?.relations ?? []), relation],
      });
    },
    [setState, canvas],
  );

  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      setState((prev: any) => {
        const nextWorkspaceDocIds = nodeId.startsWith("__doc_")
          ? (prev?.workspace_doc_ids ?? []).filter((id: string) => `__doc_${id}` !== nodeId)
          : (prev?.workspace_doc_ids ?? []);
        return {
          ...prev,
          nodes: (prev?.nodes ?? []).filter((node: any) => node.id !== nodeId),
          relations: (prev?.relations ?? []).filter(
            (rel: any) => rel.from_id !== nodeId && rel.to_id !== nodeId,
          ),
          workspace_doc_ids: nextWorkspaceDocIds,
        };
      });
    },
    [setState],
  );

  const handleAddNode = useCallback(
    (node: any, relation: { from_id: string; to_id: string; label: string } | null) => {
      const c = canvas as any;
      setState({
        ...c,
        nodes: [...(c?.nodes ?? []), node],
        relations: relation ? [...(c?.relations ?? []), relation] : (c?.relations ?? []),
      });
    },
    [setState, canvas],
  );

  const handleUpdateNode = useCallback(
    (nodeId: string, updates: Record<string, unknown>) => {
      const c = canvas as any;
      setState({
        ...c,
        nodes: (c?.nodes ?? []).map((node: any) => (node.id === nodeId ? { ...node, ...updates } : node)),
      });
    },
    [setState, canvas],
  );

  const handleSetNodeColor = useCallback(
    (nodeId: string, color: string) => {
      const c = canvas as any;
      setState({
        ...c,
        nodes: (c?.nodes ?? []).map((node: any) =>
          node.id === nodeId ? { ...node, color: color || undefined } : node,
        ),
      });
    },
    [setState, canvas],
  );

  const handleAddEdge = useCallback(
    (fromId: string, toId: string, label: string, sourceHandle?: string | null, targetHandle?: string | null) => {
      const c = canvas as any;
      const rels = c?.relations ?? [];
      if (
        rels.some(
          (rel: any) =>
            rel.from_id === fromId &&
            rel.to_id === toId &&
            (rel.source_handle ?? "") === (sourceHandle ?? "") &&
            (rel.target_handle ?? "") === (targetHandle ?? ""),
        )
      ) {
        return;
      }
      setState({
        ...c,
        relations: [
          ...rels,
          {
            from_id: fromId,
            to_id: toId,
            label,
            source_handle: sourceHandle ?? "",
            target_handle: targetHandle ?? "",
          },
        ],
      });
    },
    [setState, canvas],
  );

  const handleDeleteEdge = useCallback(
    (fromId: string, toId: string, sourceHandle?: string, targetHandle?: string) => {
      setState((prev: any) => ({
        ...prev,
        relations: (prev?.relations ?? []).filter(
          (rel: any) =>
            !(
              rel.from_id === fromId &&
              rel.to_id === toId &&
              (rel.source_handle ?? "") === (sourceHandle ?? "") &&
              (rel.target_handle ?? "") === (targetHandle ?? "")
            ),
        ),
      }));
    },
    [setState],
  );

  const handleFmuUploaded = useCallback(
    (payload: { filename: string; model_name: string; variables: any[] }, position?: FlowPosition, parentId?: string | null) => {
      const newNode = {
        id: `fmu_${Date.now()}`,
        node_type: "fmu",
        status: "found",
        title: payload.model_name || payload.filename,
        fmu_filename: payload.filename,
        fmu_model_name: payload.model_name,
        fmu_variables: payload.variables,
        fmu_param_values: {},
        last_updated_run_id: "",
        text: "",
        spec_title: "",
        properties: [],
        filename: "",
        page: 0,
        bbox: [],
        highlights: [],
        plot_job_id: "",
        plot_fmu_filename: "",
        plot_signal_names: [],
        plot_stop_time: 10,
        parent_id: parentId ?? "",
      };
      const c = canvas as any;
      setState({ ...c, nodes: [...(c?.nodes ?? []), newNode] });
      if (position) {
        persistPositions({
          ...positionsRef.current,
          [newNode.id]: position,
        });
      }
    },
    [setState, canvas, persistPositions],
  );

  const handleAddDocToWorkspace = useCallback(
    (docId: string) => {
      const c = canvas as any;
      const existing: string[] = c?.workspace_doc_ids ?? [];
      if (existing.includes(docId)) return;
      const doc = documents.find((item) => item.document_id === docId);
      if (!doc) return;
      const docNode = makeDocumentCanvasNode(doc);
      const nextNodes = (c?.nodes ?? []).some((node: any) => node.id === docNode.id)
        ? (c?.nodes ?? [])
        : [...(c?.nodes ?? []), docNode];
      setState({ ...c, nodes: nextNodes, workspace_doc_ids: [...existing, docId] });
    },
    [setState, canvas, documents],
  );

  const handleRemoveDocFromWorkspace = useCallback(
    (docId: string) => {
      const c = canvas as any;
      const existing: string[] = c?.workspace_doc_ids ?? [];
      const nodeId = `__doc_${docId}`;
      setState({
        ...c,
        nodes: (c?.nodes ?? []).filter((node: any) => node.id !== nodeId),
        relations: (c?.relations ?? []).filter((rel: any) => rel.from_id !== nodeId && rel.to_id !== nodeId),
        workspace_doc_ids: existing.filter((id: string) => id !== docId),
      });
    },
    [setState, canvas],
  );

  const handleSetParent = useCallback(
    (nodeId: string, parentId: string | null, position?: FlowPosition) => {
      const c = canvas as any;
      const nodes = (c?.nodes ?? []).map((node: any) =>
        node.id === nodeId ? { ...node, parent_id: parentId ?? "" } : node,
      );
      setState({ ...c, nodes });
      if (position) {
        persistPositions({
          ...positionsRef.current,
          [nodeId]: position,
        });
      }
    },
    [setState, canvas, persistPositions],
  );

  const handleAddSnippet = useCallback(
    (
      snippetNodes: any[],
      snippetRelations: any[],
      dropPosition?: FlowPosition,
      placements?: Array<{ id?: string; parentId: string | null; position?: FlowPosition }>,
    ) => {
      const idMap = new Map<string, string>();
      const placementMap = new Map((placements ?? []).map((item) => [item.id, item]));
      const sourcePositions = snippetNodes.map((node, index) => ({
        index,
        position:
          node?.position && typeof node.position.x === "number" && typeof node.position.y === "number"
            ? node.position
            : { x: (index % 3) * 260, y: Math.floor(index / 3) * 160 },
      }));
      const newNodes = snippetNodes.map((node) => {
        const newId = `sn_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        idMap.set(node.id, newId);
        const placement = placementMap.get(node.id);
        return { ...node, id: newId, parent_id: placement?.parentId ?? node.parent_id ?? "" };
      });
      const newRelations = snippetRelations.map((rel) => ({
        ...rel,
        from_id: idMap.get(rel.from_id) ?? rel.from_id,
        to_id: idMap.get(rel.to_id) ?? rel.to_id,
      }));
      const c = canvas as any;
      setState({
        ...c,
        nodes: [...(c?.nodes ?? []), ...newNodes],
        relations: [...(c?.relations ?? []), ...newRelations],
      });
      if (dropPosition && newNodes.length > 0) {
        const xs = sourcePositions.map((item) => item.position.x);
        const ys = sourcePositions.map((item) => item.position.y);
        const centerX = (Math.min(...xs) + Math.max(...xs)) / 2;
        const centerY = (Math.min(...ys) + Math.max(...ys)) / 2;
        const positionUpdates = Object.fromEntries(
          newNodes.map((node, index) => {
            const sourceNode = snippetNodes[index];
            const placement = sourceNode ? placementMap.get(sourceNode.id) : undefined;
            return [
              node.id,
              placement?.position ?? {
                x: sourcePositions[index]!.position.x - centerX + dropPosition.x,
                y: sourcePositions[index]!.position.y - centerY + dropPosition.y,
              },
            ];
          }),
        );
        persistPositions({
          ...positionsRef.current,
          ...positionUpdates,
        });
      }
    },
    [canvas, setState, persistPositions],
  );

  const handleFmuFromLibrary = useCallback(
    async (filename: string, position?: FlowPosition, parentId?: string | null) => {
      const c = canvas as any;
      if ((c?.nodes ?? []).some((node: any) => node.node_type === "fmu" && node.fmu_filename === filename)) return;
      try {
        const res = await fetch(`${API_URL}/api/fmu/inspect/${encodeURIComponent(filename)}`);
        if (!res.ok) return;
        const data = await res.json();
        handleFmuUploaded({ filename, model_name: data.model_name, variables: data.variables ?? [] }, position, parentId);
      } catch {
        // ignore library inspection failures
      }
    },
    [canvas, handleFmuUploaded],
  );

  const handleParameterLookup = useCallback(
    async (
      documentFilename: string,
      _modelNodeId: string,
      params: Array<{ fmuNodeId: string; paramName: string; unit?: string }>,
    ) => {
      try {
        const res = await fetch(`${API_URL}/api/documents/gold/${encodeURIComponent(documentFilename)}`);
        if (!res.ok) return;
        const gold = await res.json();
        const found = searchGoldForParams(gold, params.map((param) => param.paramName));

        const c = canvas as any;
        for (const { fmuNodeId, paramName } of params) {
          const match = found[paramName];
          if (match?.value != null) {
            const fmuNode = (c?.nodes ?? []).find((node: any) => node.id === fmuNodeId);
            if (fmuNode) {
              handleUpdateNode(fmuNodeId, {
                fmu_param_values: {
                  ...fmuNode.fmu_param_values,
                  [paramName]: String(match.value),
                },
              });
            }
          }
        }
      } catch (err) {
        console.error("Parameter lookup failed:", err);
      }
    },
    [canvas, handleUpdateNode],
  );

  const allNodes = canvas?.nodes || [];
  const allRelations = canvas?.relations || [];
  const nodeMap = new Map(allNodes.map((node: any) => [node.id, node]));
  const evidenceRelations = (allRelations as any[]).filter((rel: any) => rel.to_id?.startsWith("__doc_") && rel.page > 0);
  const contextEvidence = evidenceRelations.map((rel: any) => {
    const parentNode: any = nodeMap.get(rel.from_id);
    const doc = documents.find((item) => item.document_id === rel.document_id);
    const filename = doc?.filename ?? "";
    const page = rel.page ?? 1;
    const bbox = rel.bbox ?? [];
    const highlights: PDFHighlight[] = rel.highlights?.length > 0 ? rel.highlights : [{ page, bbox }];
    const parentLabel =
      parentNode?.node_type === "spec"
        ? parentNode.spec_title || "Specifications"
        : parentNode?.text || parentNode?.title || "Evidence";
    return {
      id: `${rel.from_id}-${rel.to_id}-${page}`,
      filename,
      page,
      bbox,
      highlights,
      previewUrl: buildEvidenceImageUrl(filename, page, bbox),
      title: parentNode?.node_type === "spec" ? parentNode.spec_title || "Specifications" : "Fact evidence",
      summary: String(parentLabel || "").replace(/\s+/g, " ").trim(),
      parentType: parentNode?.node_type === "spec" ? "spec" : "fact",
    };
  });

  const conversationsRef = useRef(conversations);
  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);
  const lastSavedConversationId = useRef<string | null>(null);

  useEffect(() => {
    if (!activeConversationId) return;
    if (lastSavedConversationId.current !== activeConversationId) {
      lastSavedConversationId.current = activeConversationId;
      return;
    }
    const persistableMessages = toPersistableChatMessages(visibleMessages as any[]);
    const currentConv = conversationsRef.current.find((conversation) => conversation.id === activeConversationId);
    if (!currentConv) return;
    const currentMessages = currentConv.messages || [];
    if (persistableMessages.length === 0 && currentMessages.length > 0) return;
    if (currentMessages.length === persistableMessages.length) {
      const lastMsgIdx = persistableMessages.length - 1;
      if (lastMsgIdx >= 0) {
        const latestVisible = persistableMessages[lastMsgIdx] as any;
        const latestStored = currentMessages[lastMsgIdx] as any;
        if (latestVisible?.id === latestStored?.id && latestVisible?.content === latestStored?.content) return;
      } else {
        return;
      }
    }
    const updates: any = {
      messages: persistableMessages,
      lastMessageAt: "Just now",
      preview: `${persistableMessages.length} messages - Just now`,
    };
    if (currentConv.title === "New Conversation" && persistableMessages.length > 0) {
      const firstUserMsg = persistableMessages.find((message) => message.role === "user");
      if (firstUserMsg) {
        const content = firstUserMsg.content;
        updates.title = content.length > 30 ? `${content.substring(0, 30)}...` : content;
      }
    }
    updateConversation(activeConversationId, updates);
  }, [visibleMessages, activeConversationId, updateConversation]);

  return {
    canvas,
    positions,
    canvasTabs,
    activeCanvasId,
    switchCanvasTab,
    addCanvasTab,
    closeCanvasTab,
    contextEvidence,
    handlers: {
      handlePositionsChange,
      handleFmuUploaded,
      handleSimulateComplete,
      handleDeleteNode,
      handleAddNode,
      handleAddEdge,
      handleDeleteEdge,
      handleSetNodeColor,
      handleUpdateNode,
      handleAddDocToWorkspace,
      handleRemoveDocFromWorkspace,
      handleSetParent,
      handleFmuFromLibrary,
      handleAddSnippet,
      handleSaveSelection,
      handleParameterLookup,
    },
  };
}

function useReadableChatMessages() {
  const { messages = [], isLoading, stopGeneration, setMessages } = useCopilotChatInternal();

  const readableMessages = useMemo(() => {
    return messages
      .map((message: any, index: number) => {
        const legacyMessage: any = aguiToGQL(message)[0];
        if (!legacyMessage) return null;
        if (
          legacyMessage?.isActionExecutionMessage?.() ||
          legacyMessage?.isAgentStateMessage?.() ||
          legacyMessage?.isResultMessage?.() ||
          legacyMessage?.isImageMessage?.()
        ) {
          return null;
        }
        const rawContent = legacyMessage.content ?? message.content ?? "";
        const content =
          typeof rawContent === "string"
            ? rawContent
            : Array.isArray(rawContent)
              ? rawContent.map((part: any) => part?.text ?? "").join(" ")
              : String(rawContent ?? "");
        if (!content.trim()) return null;
        return {
          id: legacyMessage.id ?? message.id ?? `${legacyMessage.role}-${index}`,
          role: legacyMessage.role ?? message.role,
          content,
          sourceIndex: index,
        };
      })
      .filter(Boolean) as Array<{ id: string; role: string; content: string; sourceIndex: number }>;
  }, [messages]);

  const updateMessageContent = useCallback(
    (messageId: string, sourceIndex: number, content: string) => {
      const next = messages.map((message: any, index: number) => {
        const legacyMessage: any = aguiToGQL(message)[0];
        const readableId = legacyMessage?.id ?? message?.id ?? `${legacyMessage?.role ?? message?.role}-${index}`;
        if (index !== sourceIndex && readableId !== messageId && message?.id !== messageId) {
          return message;
        }
        return {
          ...message,
          content,
        };
      });
      setMessages(next as any);
    },
    [messages, setMessages],
  );

  const recentActions = useMemo(() => {
    const actions: string[] = [];
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const legacyMessage: any = aguiToGQL(messages[index] as any)[0];
      if (!legacyMessage) continue;
      if (legacyMessage?.role === "user") break;
      if (legacyMessage.isActionExecutionMessage?.()) {
        const name = legacyMessage.name || "tool";
        const args = (() => {
          if (typeof legacyMessage.arguments !== "string") return legacyMessage.arguments;
          try {
            return JSON.parse(legacyMessage.arguments);
          } catch {
            return {};
          }
        })();
        const page = typeof args?.page_no === "number" ? ` page ${args.page_no}` : "";
        const filename = typeof args?.filename === "string" ? ` ${args.filename}` : "";
        const label =
          name === "read_document_page"
            ? `Reading${filename}${page}`
            : name === "get_document_tree"
              ? `Opening document index${filename}`
              : name === "get_document_full_text"
                ? `Loading document text${filename}`
                : name === "add_spec_node"
                  ? "Adding grounded table"
                  : name === "add_fact"
                    ? "Adding fact"
                    : `Calling ${name}`;
        if (!actions.includes(label)) actions.push(label);
        if (actions.length >= 4) break;
      }
    }
    return actions;
  }, [messages]);

  return { messages: readableMessages, recentActions, isLoading, stopGeneration, updateMessageContent };
}

function WorkspaceTopBar({
  selectedModel,
  onModelChange,
  models,
}: {
  selectedModel: string;
  onModelChange: (id: string) => void;
  models: ModelOption[];
}) {
  const { documents, conversations, activeConversationId, createNewConversation, setActiveConversationId } = useApp();
  const activeConversation = conversations.find((conversation) => conversation.id === activeConversationId);

  const handleNewWorkspace = useCallback(async () => {
    const id = await createNewConversation();
    setActiveConversationId(id);
  }, [createNewConversation, setActiveConversationId]);

  return (
    <div className="absolute left-4 right-4 top-3 z-30 flex h-12 items-center justify-between gap-3 rounded-lg border border-neutral-200/80 bg-white/92 px-3 shadow-sm backdrop-blur-md dark:border-neutral-800/80 dark:bg-neutral-950/88">
      <div className="flex min-w-0 items-center gap-3">
        <div
          className="flex h-8 w-8 items-center justify-center rounded-md border border-neutral-200 bg-white text-neutral-700 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-200"
          title="Anchor workspace"
        >
          <Network size={15} />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-neutral-900 dark:text-neutral-100">
              {activeConversation?.title || "Anchor workspace"}
            </span>
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
              medallion
            </span>
          </div>
          <p className="truncate text-[11px] text-neutral-500 dark:text-neutral-400">
            {documents.length} document{documents.length === 1 ? "" : "s"} in knowledge base
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={handleNewWorkspace}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-neutral-200 bg-white px-2.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          <Plus size={13} />
          New
        </button>
        <AgSelect
          options={models.filter((model) => model.type === "chat" || !model.type)}
          value={selectedModel}
          onChange={onModelChange}
          align="right"
          className="hidden min-w-[220px] sm:block"
          icon={<Cpu size={14} />}
        />
      </div>
    </div>
  );
}

function WorkspaceAssetRail({ controller }: { controller: Controller }) {
  const [openPalette, setOpenPalette] = useState<PaletteTab | null>(null);
  const buttons: Array<{ id: PaletteTab; icon: React.ReactNode; label: string }> = [
    { id: "docs", icon: <FileText size={16} />, label: "Documents" },
    { id: "fmus", icon: <Cpu size={16} />, label: "FMUs" },
    { id: "snippets", icon: <Layers size={16} />, label: "Snippets" },
  ];

  return (
    <>
      <div className="absolute left-4 top-20 z-30 flex flex-col gap-2 rounded-lg border border-neutral-200/80 bg-white/92 p-2 shadow-sm backdrop-blur-md dark:border-neutral-800/80 dark:bg-neutral-950/88">
        {buttons.map((button) => (
          <button
            key={button.id}
            onClick={() => setOpenPalette((current) => (current === button.id ? null : button.id))}
            className={`flex h-10 w-10 items-center justify-center rounded-md transition-colors ${
              openPalette === button.id
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-900 dark:hover:text-neutral-100"
            }`}
            title={button.label}
          >
            {button.icon}
          </button>
        ))}
      </div>
      {openPalette && (
        <ResourcePalette
          tab={openPalette}
          anchorY={80}
          workspaceDocIds={controller.canvas?.workspace_doc_ids ?? []}
          onAddDoc={controller.handlers.handleAddDocToWorkspace}
          onAddFmu={controller.handlers.handleFmuFromLibrary}
          onAddSnippet={controller.handlers.handleAddSnippet}
          onClose={() => setOpenPalette(null)}
        />
      )}
    </>
  );
}

function WorkspaceTabs({ controller }: { controller: Controller }) {
  return (
    <div className="absolute left-20 top-20 z-20 flex max-w-[calc(100vw-32rem)] items-center gap-1 overflow-x-auto rounded-lg border border-neutral-200/80 bg-white/90 p-1 shadow-sm backdrop-blur-md dark:border-neutral-800/80 dark:bg-neutral-950/88">
      {controller.canvasTabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => controller.switchCanvasTab(tab.id)}
          className={`group inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors ${
            tab.id === controller.activeCanvasId
              ? "bg-neutral-100 text-neutral-950 dark:bg-neutral-900 dark:text-neutral-100"
              : "text-neutral-500 hover:bg-neutral-50 hover:text-neutral-800 dark:text-neutral-400 dark:hover:bg-neutral-900 dark:hover:text-neutral-200"
          }`}
        >
          <span className="max-w-[96px] truncate">{tab.name}</span>
          {controller.canvasTabs.length > 1 && (
            <span
              role="button"
              tabIndex={0}
              onClick={(event) => {
                event.stopPropagation();
                controller.closeCanvasTab(tab.id);
              }}
              className="rounded p-0.5 opacity-0 hover:text-red-500 group-hover:opacity-100"
            >
              <X size={10} />
            </span>
          )}
        </button>
      ))}
      <button
        onClick={controller.addCanvasTab}
        className="flex h-8 w-8 items-center justify-center rounded-md text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-900 dark:hover:text-neutral-200"
        title="New canvas"
      >
        <Plus size={13} />
      </button>
    </div>
  );
}

function WorkspaceComposer({ onOpenActivity }: { onOpenActivity: () => void }) {
  const [text, setText] = useState("");
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);
  const {
    documents,
    activeDocumentId,
    setActiveDocumentId,
    refreshDocuments,
    focusedChatNodes,
    removeFocusedChatNode,
    clearFocusedChatNodes,
  } = useApp();
  const { sendMessage, isLoading, stopGeneration } = useCopilotChatInternal();
  const activeDoc = documents.find((document) => document.document_id === activeDocumentId) ?? null;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 136)}px`;
  }, [text]);

  useEffect(() => {
    if (!docPickerOpen) return;
    const handler = (event: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setDocPickerOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [docPickerOpen]);

  const uploadFiles = useCallback(
    async (files: File[]) => {
      for (const file of files) {
        setUploadingFiles((previous) => [...previous, { file, status: "uploading" }]);
        try {
          const formData = new FormData();
          formData.append("file", file);
          const res = await fetch(`${API_URL}/api/documents/upload`, {
            method: "POST",
            body: formData,
          });
          if (!res.ok) throw new Error("Upload failed");
          setUploadingFiles((previous) =>
            previous.map((entry) => (entry.file === file ? { ...entry, status: "success" } : entry)),
          );
          await refreshDocuments();
          setTimeout(() => {
            setUploadingFiles((previous) => previous.filter((entry) => entry.file !== file));
          }, 3000);
        } catch (err) {
          setUploadingFiles((previous) =>
            previous.map((entry) =>
              entry.file === file
                ? {
                    ...entry,
                    status: "error",
                    error: err instanceof Error ? err.message : "Upload failed",
                  }
                : entry,
            ),
          );
          setTimeout(() => {
            setUploadingFiles((previous) => previous.filter((entry) => entry.file !== file));
          }, 5000);
        }
      }
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [refreshDocuments],
  );

  const handleSend = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    setText("");
    onOpenActivity();
    await sendMessage({
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
    });
  }, [text, isLoading, onOpenActivity, sendMessage]);

  return (
    <div className="absolute bottom-5 left-1/2 z-30 w-[min(760px,calc(100vw-2rem))] -translate-x-1/2">
      {uploadingFiles.length > 0 && (
        <div className="mb-2 space-y-1">
          {uploadingFiles.map((upload, index) => (
            <div
              key={`${upload.file.name}-${index}`}
              className={`flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs shadow-sm ${
                upload.status === "uploading"
                  ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-200"
                  : upload.status === "success"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200"
                    : "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
              }`}
            >
              {upload.status === "uploading" ? <Loader2 size={12} className="animate-spin" /> : <FileText size={12} />}
              <span className="min-w-0 flex-1 truncate">{upload.file.name}</span>
              <span>{upload.status === "uploading" ? "Uploading" : upload.status === "success" ? "Added" : upload.error}</span>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-lg border border-neutral-200/90 bg-white/96 p-2 shadow-[0_18px_60px_rgba(15,23,42,0.16)] backdrop-blur-md dark:border-neutral-800/90 dark:bg-neutral-950/94">
        <div className="mb-2 flex flex-wrap items-center gap-2 px-1" ref={pickerRef}>
          <button
            type="button"
            onClick={() => setDocPickerOpen((open) => !open)}
            className={`inline-flex h-7 max-w-[220px] items-center gap-1.5 rounded-full border px-2.5 text-xs ${
              activeDoc
                ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                : "border-neutral-200 bg-neutral-100 text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300"
            }`}
          >
            <FileText size={11} />
            <span className="truncate">{activeDoc ? activeDoc.filename : "All documents"}</span>
            <ChevronDown size={11} />
          </button>
          {docPickerOpen && (
            <div className="absolute bottom-full left-2 mb-2 max-h-72 w-72 overflow-y-auto rounded-lg border border-neutral-200 bg-white p-1 shadow-lg dark:border-neutral-800 dark:bg-neutral-950">
              <button
                className="w-full rounded-md px-3 py-2 text-left text-xs text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-900"
                onClick={() => {
                  setActiveDocumentId(null);
                  setDocPickerOpen(false);
                }}
              >
                All documents
              </button>
              {documents.map((document) => (
                <button
                  key={document.document_id}
                  className={`w-full truncate rounded-md px-3 py-2 text-left text-xs hover:bg-neutral-100 dark:hover:bg-neutral-900 ${
                    document.document_id === activeDocumentId
                      ? "font-medium text-emerald-700 dark:text-emerald-300"
                      : "text-neutral-700 dark:text-neutral-300"
                  }`}
                  onClick={() => {
                    setActiveDocumentId(document.document_id);
                    setDocPickerOpen(false);
                  }}
                  title={document.filename}
                >
                  {document.filename}
                </button>
              ))}
            </div>
          )}
          {focusedChatNodes.map((node) => (
            <span
              key={node.nodeId}
              className="inline-flex h-7 max-w-[220px] items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2.5 text-xs text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300"
            >
              <span className="truncate">{node.title || node.nodeType}</span>
              <button onClick={() => removeFocusedChatNode(node.nodeId)} className="rounded-full p-0.5 hover:bg-blue-100 dark:hover:bg-blue-900">
                <X size={10} />
              </button>
            </span>
          ))}
          {focusedChatNodes.length > 1 && (
            <button onClick={clearFocusedChatNodes} className="text-xs text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100">
              Clear
            </button>
          )}
        </div>

        <div className="flex items-end gap-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="mb-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-900 dark:hover:text-neutral-100"
            title="Upload document"
          >
            <Paperclip size={17} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md,.html"
            multiple
            onChange={(event) => {
              const files = event.target.files;
              if (files?.length) void uploadFiles(Array.from(files));
            }}
            className="hidden"
          />
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
            placeholder="Ask Anchor to extract, compare, place, or wire document-backed data"
            rows={1}
            className="max-h-[136px] min-h-[42px] flex-1 resize-none border-0 bg-transparent px-1 py-2.5 text-sm text-neutral-900 outline-none placeholder:text-neutral-400 focus:ring-0 dark:text-neutral-100"
          />
          {isLoading ? (
            <button
              type="button"
              onClick={stopGeneration}
              className="mb-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-neutral-900 text-white hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
              title="Stop"
            >
              <StopCircle size={17} />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={!text.trim()}
              className="mb-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-neutral-900 text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-200 disabled:text-neutral-400 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300 dark:disabled:bg-neutral-800 dark:disabled:text-neutral-500"
              title="Send"
            >
              <ArrowUp size={17} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ActivityDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { messages, recentActions, isLoading, updateMessageContent } = useReadableChatMessages();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  if (!open) return null;

  const startEditing = (message: { id: string; content: string }) => {
    setEditingId(message.id);
    setDraft(message.content);
  };

  const commitEdit = (message: { id: string; sourceIndex: number; content: string }) => {
    const next = draft.trim();
    if (next && next !== message.content) {
      updateMessageContent(message.id, message.sourceIndex, next);
    }
    setEditingId(null);
    setDraft("");
  };

  return (
    <div className="absolute bottom-[8.75rem] left-1/2 z-30 flex h-[min(360px,calc(100vh-13rem))] w-[min(760px,calc(100vw-2rem))] -translate-x-1/2 flex-col overflow-hidden rounded-lg border border-neutral-200 bg-white/96 shadow-xl backdrop-blur-md dark:border-neutral-800 dark:bg-neutral-950/94">
      <div className="flex h-11 items-center justify-between border-b border-neutral-200 px-3 dark:border-neutral-800">
        <div className="flex items-center gap-2 text-sm font-medium text-neutral-800 dark:text-neutral-100">
          {isLoading ? <Loader2 size={15} className="animate-spin text-blue-500" /> : <MessageSquare size={15} />}
          Activity
        </div>
        <button onClick={onClose} className="rounded-md p-1.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-800 dark:hover:bg-neutral-900 dark:hover:text-neutral-100">
          <X size={15} />
        </button>
      </div>
      {recentActions.length > 0 && (
        <div className="border-b border-neutral-200 bg-blue-50/70 px-3 py-2 dark:border-neutral-800 dark:bg-blue-950/20">
          <div className="flex flex-wrap gap-1.5">
            {recentActions.map((action) => (
              <span key={action} className="rounded-full border border-blue-200 bg-white px-2 py-1 text-[11px] text-blue-700 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-200">
                {action}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-neutral-400">
            No messages yet.
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              draggable={message.role === "assistant" && editingId !== message.id}
              onDragStart={(event) => {
                if (message.role !== "assistant") return;
                const content = editingId === message.id ? draft : message.content;
                event.dataTransfer.setData(
                  "application/anchor-chat-message",
                  JSON.stringify({
                    id: message.id,
                    role: message.role,
                    title: "Explanation",
                    content,
                  }),
                );
                event.dataTransfer.setData("text/plain", content);
                event.dataTransfer.effectAllowed = "copy";
              }}
              className={`group max-w-[86%] rounded-lg px-3 py-2 text-sm leading-6 ${
                message.role === "user"
                  ? "ml-auto bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                  : "mr-auto border border-neutral-200 bg-neutral-50 text-neutral-800 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-100"
              } ${message.role === "assistant" && editingId !== message.id ? "cursor-grab active:cursor-grabbing" : ""}`}
              title={message.role === "assistant" ? "Drag onto the canvas to create an editable fact node." : undefined}
            >
              {editingId === message.id ? (
                <div className="space-y-2">
                  <textarea
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      event.stopPropagation();
                      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                        commitEdit(message);
                      }
                      if (event.key === "Escape") {
                        setEditingId(null);
                        setDraft("");
                      }
                    }}
                    className="min-h-24 w-full resize-y rounded-md border border-neutral-200 bg-white p-2 text-sm leading-6 text-neutral-800 outline-none focus:border-blue-300 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
                    autoFocus
                  />
                  <div className="flex justify-end gap-1.5">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(null);
                        setDraft("");
                      }}
                      className="rounded-md px-2 py-1 text-xs text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => commitEdit(message)}
                      className="inline-flex items-center gap-1 rounded-md bg-neutral-900 px-2 py-1 text-xs font-medium text-white hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
                    >
                      <Check size={12} />
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-2">
                  {message.role === "assistant" && (
                    <GripVertical size={14} className="mt-1 shrink-0 text-neutral-300 opacity-0 transition-opacity group-hover:opacity-100 dark:text-neutral-600" />
                  )}
                  <div className="min-w-0 flex-1 whitespace-pre-wrap">{message.content}</div>
                  {message.role === "assistant" && (
                    <button
                      type="button"
                      onClick={() => startEditing(message)}
                      className="mt-0.5 shrink-0 rounded-md p-1 text-neutral-400 opacity-0 transition-opacity hover:bg-neutral-100 hover:text-neutral-800 group-hover:opacity-100 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
                      title="Edit explanation"
                    >
                      <Pencil size={12} />
                    </button>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function MedallionInspector({
  controller,
  onOpenPdf,
  isOpen,
  onToggle,
}: {
  controller: Controller;
  onOpenPdf: (state: { filename: string; page: number; highlights: PDFHighlight[] }) => void;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const { documents } = useApp();
  const workspaceDocIds: string[] = controller.canvas?.workspace_doc_ids ?? [];
  const workspaceDocs = workspaceDocIds
    .map((id) => documents.find((document) => document.document_id === id))
    .filter(Boolean) as Array<{ document_id: string; filename: string; node_count: number; status?: string }>;
  const docsForPanel = workspaceDocs.length > 0 ? workspaceDocs : documents;
  const [selectedFilename, setSelectedFilename] = useState("");
  const [detail, setDetail] = useState<PipelineDetail | null>(null);

  useEffect(() => {
    const first = docsForPanel[0]?.filename ?? "";
    setSelectedFilename((current) => current || first);
  }, [docsForPanel]);

  useEffect(() => {
    if (!selectedFilename) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    fetch(`${API_URL}/api/documents/pipeline-detail/${encodeURIComponent(selectedFilename)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedFilename]);

  const goldRegions = detail?.gold?.pages?.reduce((sum, page) => sum + (page.region_count ?? 0), 0) ?? 0;

  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className="absolute right-4 top-20 z-20 hidden h-10 items-center gap-2 rounded-lg border border-neutral-200/80 bg-white/92 px-3 text-xs font-medium text-neutral-700 shadow-sm backdrop-blur-md hover:bg-neutral-50 dark:border-neutral-800/80 dark:bg-neutral-950/88 dark:text-neutral-200 dark:hover:bg-neutral-900 xl:inline-flex"
        title="Show medallion panel"
      >
        <PanelRight size={14} />
        Medallion
      </button>
    );
  }

  return (
    <div className="absolute bottom-5 right-4 top-20 z-20 hidden w-80 flex-col overflow-hidden rounded-lg border border-neutral-200/80 bg-white/92 shadow-sm backdrop-blur-md dark:border-neutral-800/80 dark:bg-neutral-950/88 xl:flex">
      <div className="flex h-12 items-center justify-between border-b border-neutral-200 px-3 dark:border-neutral-800">
        <div className="flex items-center gap-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">
          <Database size={15} />
          Medallion
        </div>
        <button
          onClick={onToggle}
          className="rounded-md p-1.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-800 dark:hover:bg-neutral-900 dark:hover:text-neutral-100"
          title="Minimize medallion panel"
        >
          <PanelRight size={15} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-neutral-400">
          Document
        </label>
        <select
          value={selectedFilename}
          onChange={(event) => setSelectedFilename(event.target.value)}
          className="mb-3 h-9 w-full rounded-md border border-neutral-200 bg-white px-2 text-xs text-neutral-800 dark:border-neutral-800 dark:bg-neutral-950 dark:text-neutral-100"
        >
          {docsForPanel.map((document) => (
            <option key={document.document_id} value={document.filename}>
              {document.filename}
            </option>
          ))}
        </select>

        <div className="grid grid-cols-3 gap-2">
          <MedallionStat label="Bronze" value={detail?.bronze ? "ready" : "none"} tone={detail?.bronze ? "emerald" : "neutral"} />
          <MedallionStat label="Silver" value={detail?.silver ? `${detail.silver.page_count ?? 0} pg` : "none"} tone={detail?.silver ? "blue" : "neutral"} />
          <MedallionStat label="Gold" value={detail?.gold ? `${goldRegions}` : "none"} tone={detail?.gold ? "amber" : "neutral"} />
        </div>

        {detail?.status && (
          <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 p-2 text-xs text-blue-700 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-200">
            {detail.status.stage} {detail.status.total ? `${detail.status.current}/${detail.status.total}` : ""}
          </div>
        )}

        <div className="mt-4 space-y-3">
          <div>
            <h3 className="mb-2 text-xs font-semibold text-neutral-700 dark:text-neutral-200">Silver index</h3>
            <div className="grid grid-cols-3 gap-2 text-center">
              <SmallMetric label="Outline" value={detail?.silver?.outline_count ?? 0} />
              <SmallMetric label="Tables" value={detail?.silver?.table_count ?? 0} />
              <SmallMetric label="Figures" value={detail?.silver?.figure_count ?? 0} />
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold text-neutral-700 dark:text-neutral-200">Gold regions</h3>
            {detail?.gold?.pages?.length ? (
              <div className="space-y-1">
                {detail.gold.pages.map((page) => (
                  <div
                    key={page.page}
                    className="flex items-center justify-between rounded-md border border-neutral-200 bg-neutral-50 px-2 py-1.5 text-xs dark:border-neutral-800 dark:bg-neutral-900"
                  >
                    <span className="text-neutral-600 dark:text-neutral-300">Page {page.page}</span>
                    <span className="text-neutral-400">{page.region_count} regions</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-md border border-neutral-200 bg-neutral-50 p-2 text-xs text-neutral-400 dark:border-neutral-800 dark:bg-neutral-900">
                No gold regions available.
              </p>
            )}
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold text-neutral-700 dark:text-neutral-200">Canvas evidence</h3>
            {controller.contextEvidence.length > 0 ? (
              <div className="space-y-2">
                {controller.contextEvidence.slice(0, 4).map((evidence: any) => (
                  <button
                    key={evidence.id}
                    onClick={() =>
                      onOpenPdf({
                        filename: evidence.filename,
                        page: evidence.page,
                        highlights: evidence.highlights,
                      })
                    }
                    className="flex w-full items-center gap-2 rounded-md border border-neutral-200 bg-white p-2 text-left hover:bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-950 dark:hover:bg-neutral-900"
                  >
                    <div className="h-10 w-12 shrink-0 overflow-hidden rounded bg-neutral-100 dark:bg-neutral-900">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={evidence.previewUrl} alt="" className="h-full w-full object-cover" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium text-neutral-800 dark:text-neutral-100">{evidence.title}</p>
                      <p className="truncate text-[11px] text-neutral-400">p.{evidence.page}</p>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <p className="rounded-md border border-neutral-200 bg-neutral-50 p-2 text-xs text-neutral-400 dark:border-neutral-800 dark:bg-neutral-900">
                No row-level evidence edges yet.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MedallionStat({ label, value, tone }: { label: string; value: string; tone: "emerald" | "blue" | "amber" | "neutral" }) {
  const toneClass =
    tone === "emerald"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300"
      : tone === "blue"
        ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300"
        : tone === "amber"
          ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300"
          : "border-neutral-200 bg-neutral-50 text-neutral-400 dark:border-neutral-800 dark:bg-neutral-900";
  return (
    <div className={`rounded-md border p-2 ${toneClass}`}>
      <p className="text-[10px] uppercase tracking-wide opacity-75">{label}</p>
      <p className="mt-1 text-xs font-semibold">{value}</p>
    </div>
  );
}

function SmallMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-neutral-200 bg-neutral-50 p-2 dark:border-neutral-800 dark:bg-neutral-900">
      <p className="text-sm font-semibold text-neutral-800 dark:text-neutral-100">{value}</p>
      <p className="text-[10px] text-neutral-400">{label}</p>
    </div>
  );
}

function WorkspaceV2Content() {
  const controller = useWorkspaceV2Controller();
  const [activityOpen, setActivityOpen] = useState(false);
  const [medallionOpen, setMedallionOpen] = useState(true);
  const [contextPdf, setContextPdf] = useState<{
    filename: string;
    page: number;
    highlights: PDFHighlight[];
  } | null>(null);

  return (
    <div className="relative h-full min-h-0 flex-1 overflow-hidden bg-neutral-50 text-neutral-950 dark:bg-neutral-950 dark:text-neutral-50">
      <CanvasGraph
        canvas={controller.canvas}
        initialPositions={controller.positions}
        onPositionsChange={controller.handlers.handlePositionsChange}
        showInternalToolbar={false}
        onFmuUploaded={controller.handlers.handleFmuUploaded}
        onSimulateComplete={controller.handlers.handleSimulateComplete}
        onDeleteNode={controller.handlers.handleDeleteNode}
        onAddNode={controller.handlers.handleAddNode}
        onAddEdge={controller.handlers.handleAddEdge}
        onDeleteEdge={controller.handlers.handleDeleteEdge}
        onSetNodeColor={controller.handlers.handleSetNodeColor}
        onUpdateNode={controller.handlers.handleUpdateNode}
        workspaceDocIds={controller.canvas?.workspace_doc_ids ?? []}
        onAddDocToWorkspace={controller.handlers.handleAddDocToWorkspace}
        onRemoveDocFromWorkspace={controller.handlers.handleRemoveDocFromWorkspace}
        onSetParent={controller.handlers.handleSetParent}
        onFmuFromLibrary={controller.handlers.handleFmuFromLibrary}
        onAddSnippet={controller.handlers.handleAddSnippet}
        onSaveSelection={controller.handlers.handleSaveSelection}
        onParameterLookup={controller.handlers.handleParameterLookup}
      />

      <WorkspaceAssetRail controller={controller} />
      <WorkspaceTabs controller={controller} />

      <button
        onClick={() => setActivityOpen((open) => !open)}
        className="absolute bottom-[8.75rem] right-4 z-30 inline-flex h-10 items-center gap-2 rounded-lg border border-neutral-200 bg-white/92 px-3 text-xs font-medium text-neutral-700 shadow-sm backdrop-blur-md hover:bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-950/88 dark:text-neutral-200 dark:hover:bg-neutral-900 xl:right-[22rem]"
      >
        <Activity size={14} />
        Activity
      </button>

      <WorkspaceComposer onOpenActivity={() => setActivityOpen(true)} />
      <ActivityDrawer open={activityOpen} onClose={() => setActivityOpen(false)} />
      <MedallionInspector
        controller={controller}
        onOpenPdf={setContextPdf}
        isOpen={medallionOpen}
        onToggle={() => setMedallionOpen((open) => !open)}
      />

      {contextPdf && (
        <PDFModal
          filename={contextPdf.filename}
          initialPage={contextPdf.page}
          highlights={contextPdf.highlights}
          onClose={() => setContextPdf(null)}
        />
      )}
    </div>
  );
}

interface WorkspaceV2AppProps {
  initialThreadId?: string;
}

export function WorkspaceV2App({ initialThreadId }: WorkspaceV2AppProps) {
  const router = useRouter();
  const pathname = usePathname();
  const {
    selectedModel,
    setSelectedModel,
    activeConversationId,
    setActiveConversationId,
  } = useApp();
  const [models, setModels] = useState<ModelOption[]>([]);

  useEffect(() => {
    if (!initialThreadId) return;
    setActiveConversationId(initialThreadId);
  }, [initialThreadId, setActiveConversationId]);

  useEffect(() => {
    if (!activeConversationId) return;
    const targetPath = `/c/${activeConversationId}`;
    if (pathname !== targetPath) {
      router.replace(targetPath);
    }
  }, [activeConversationId, pathname, router]);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        const res = await fetch(`${API_URL}/api/models`);
        if (!res.ok) return;
        const data = await res.json();
        const normalizedModels = normalizeModelOptions(data.models);
        if (normalizedModels.length > 0) {
          setModels(normalizedModels);
          const currentExists = normalizedModels.some((model) => model.id === selectedModel);
          if (!currentExists && normalizedModels[0]) {
            setSelectedModel(normalizedModels[0].id);
          }
        }
      } catch {
        // backend offline
      }
    };
    void fetchModels();
  }, [selectedModel, setSelectedModel]);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-neutral-50 font-sans text-neutral-950 dark:bg-neutral-950 dark:text-neutral-50">
      <CopilotKit
        runtimeUrl={`/api/copilotkit?model=${selectedModel}`}
        agent="my_agent"
        threadId={activeConversationId}
      >
        <ConversationRestorer />
        <WorkspaceTopBar
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          models={models}
        />
        <WorkspaceV2Content />
      </CopilotKit>
    </div>
  );
}
