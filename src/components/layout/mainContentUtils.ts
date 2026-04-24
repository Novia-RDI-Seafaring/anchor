import { API_URL } from "@/lib/api-config";

export type CanvasState = {
  nodes: any[];
  relations: any[];
  active_document_id: string | null;
  workspace_doc_ids?: string[];
  focused_chat_nodes?: Array<{
    node_id: string;
    node_type: string;
    title?: string;
    summary?: string;
    filename?: string;
    page?: number;
    bbox?: number[];
  }>;
};

export type CanvasTab = {
  id: string;
  name: string;
  nodes: any[];
  relations: any[];
  positions: Record<string, { x: number; y: number }>;
};

export type FlowPosition = { x: number; y: number };

type DocumentSummary = {
  document_id: string;
  filename: string;
  node_count: number;
  status?: string;
};

export function searchGoldForParams(
  gold: any,
  paramNames: string[],
): Record<string, { value: string; unit?: string; page?: number }> {
  const results: Record<string, { value: string; unit?: string; page?: number }> = {};
  const loweredNames = paramNames.map((name) => name.toLowerCase().replace(/[_-]/g, " "));

  function visitSection(section: any) {
    if (section.rows) {
      for (const row of section.rows) {
        const rowParam = (row.parameter ?? row.label ?? "").toLowerCase().replace(/[_-]/g, " ");
        for (let index = 0; index < loweredNames.length; index += 1) {
          const lowered = loweredNames[index]!;
          const original = paramNames[index]!;
          if ((rowParam.includes(lowered) || lowered.includes(rowParam)) && row.value != null && !results[original]) {
            results[original] = { value: String(row.value), unit: row.unit, page: section.page };
          }
        }
      }
    }

    if (section.properties && typeof section.properties === "object") {
      for (const [key, value] of Object.entries(section.properties)) {
        const keyLower = key.toLowerCase().replace(/[_-]/g, " ");
        for (let index = 0; index < loweredNames.length; index += 1) {
          const lowered = loweredNames[index]!;
          const original = paramNames[index]!;
          if ((keyLower.includes(lowered) || lowered.includes(keyLower)) && value != null && !results[original]) {
            results[original] =
              typeof value === "object" && value !== null && "value" in value
                ? { value: String((value as any).value), unit: (value as any).unit, page: section.page }
                : { value: String(value), page: section.page };
          }
        }
      }
    }

    if (section.subsections) {
      for (const subsection of section.subsections) visitSection(subsection);
    }
  }

  for (const section of gold.sections ?? []) visitSection(section);
  return results;
}

export function makeDocumentCanvasNode(doc: DocumentSummary) {
  return {
    id: `__doc_${doc.document_id}`,
    node_type: "document",
    status:
      doc.status === "processing" || doc.status === "pending"
        ? "searching"
        : doc.status === "error" || doc.status === "failed"
          ? "not_found"
          : "found",
    title: doc.filename,
    text: "",
    spec_title: "",
    properties: [],
    filename: doc.filename,
    page: 0,
    bbox: [],
    highlights: [],
    fmu_filename: "",
    fmu_model_name: "",
    fmu_variables: [],
    fmu_param_values: {},
    plot_job_id: "",
    plot_fmu_filename: "",
    plot_signal_names: [],
    plot_stop_time: 10,
    plot_param_values: {},
    funnel_label: "",
    area_label: "",
    area_width: 0,
    area_height: 0,
    width: 150,
    height: 64,
    parent_id: "",
    last_updated_run_id: "",
  };
}

export function materializeWorkspaceDocuments(
  nodes: any[],
  workspaceDocIds: string[] | undefined,
  documents: DocumentSummary[],
) {
  const ids = workspaceDocIds ?? [];
  if (ids.length === 0) return nodes;

  const existingIds = new Set(nodes.map((node: any) => node.id));
  const hydrated = [...nodes];
  for (const docId of ids) {
    const nodeId = `__doc_${docId}`;
    if (existingIds.has(nodeId)) continue;
    const doc = documents.find((item) => item.document_id === docId);
    if (!doc) continue;
    hydrated.push(makeDocumentCanvasNode(doc));
  }
  return hydrated;
}

export function buildEvidenceImageUrl(filename: string, page: number, bbox: number[]): string {
  const [left = 0, top = 0, right = 0, bottom = 0] = bbox;
  if (!left && !top && !right && !bottom) {
    return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}`;
  }
  return `${API_URL}/api/documents/pdf/screenshot?filename=${encodeURIComponent(filename)}&page_no=${page}&bbox_l=${left}&bbox_t=${top}&bbox_r=${right}&bbox_b=${bottom}`;
}

export function makeTabId() {
  return `cv_${Date.now()}`;
}

export function createDefaultCanvasTab(): CanvasTab {
  return { id: "default", name: "Canvas 1", nodes: [], relations: [], positions: {} };
}

export function mergeActiveCanvasTab(
  tabs: CanvasTab[],
  activeTabId: string,
  activeNodes: any[],
  activeRelations: any[],
  activePositions: Record<string, { x: number; y: number }>,
): CanvasTab[] {
  return tabs.map((tab) =>
    tab.id === activeTabId
      ? { ...tab, nodes: activeNodes, relations: activeRelations, positions: activePositions }
      : tab,
  );
}

export function buildCanvasStatePayload(
  tabs: CanvasTab[],
  activeTabId: string,
  activeNodes: any[],
  activeRelations: any[],
  activePositions: Record<string, { x: number; y: number }>,
  workspaceDocIds: string[],
) {
  return {
    tabs: mergeActiveCanvasTab(tabs, activeTabId, activeNodes, activeRelations, activePositions),
    activeTabId,
    workspace_doc_ids: workspaceDocIds,
  };
}

export function createCanvasTab(index: number, id = makeTabId()): CanvasTab {
  return {
    id,
    name: `Canvas ${index}`,
    nodes: [],
    relations: [],
    positions: {},
  };
}

export function normalizeSavedCanvasState(
  canvasState: any,
  documents: DocumentSummary[],
) {
  if (canvasState && Object.keys(canvasState).length > 0) {
    if (canvasState.tabs && Array.isArray(canvasState.tabs)) {
      const tabs: CanvasTab[] = canvasState.tabs;
      const activeTabId = canvasState.activeTabId ?? tabs[0]?.id ?? "default";
      const activeTab = tabs.find((tab) => tab.id === activeTabId) ?? tabs[0] ?? createDefaultCanvasTab();
      return {
        tabs,
        activeTabId,
        positions: activeTab.positions ?? {},
        nodes: materializeWorkspaceDocuments(activeTab.nodes ?? [], canvasState.workspace_doc_ids, documents),
        relations: activeTab.relations ?? [],
        workspaceDocIds: canvasState.workspace_doc_ids ?? [],
      };
    }

    const legacyTab: CanvasTab = {
      id: "default",
      name: "Canvas 1",
      nodes: canvasState.nodes ?? [],
      relations: canvasState.relations ?? [],
      positions: canvasState.positions ?? {},
    };
    return {
      tabs: [legacyTab],
      activeTabId: "default",
      positions: legacyTab.positions,
      nodes: materializeWorkspaceDocuments(legacyTab.nodes, canvasState.workspace_doc_ids, documents),
      relations: legacyTab.relations,
      workspaceDocIds: canvasState.workspace_doc_ids ?? [],
    };
  }

  const emptyTab = createDefaultCanvasTab();
  return {
    tabs: [emptyTab],
    activeTabId: "default",
    positions: {},
    nodes: [],
    relations: [],
    workspaceDocIds: [],
  };
}
