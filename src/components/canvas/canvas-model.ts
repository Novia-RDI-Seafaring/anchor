import type { KBDocument } from "@/contexts/AppContext";

export type NodeStatus = "pending" | "searching" | "found" | "partial" | "not_found";

export interface ParameterSource {
  doc_id?: string;
  filename?: string;
  page?: number;
  bbox?: number[];
}

export interface ParameterRow {
  parameter: string;
  value: string;
  unit?: string;
  source?: ParameterSource;
}

export interface ParameterSection {
  name: string;
  rows: ParameterRow[];
}

export interface SpecProperty {
  key: string;
  value: string;
  unit?: string;
  group?: string;
  left_label?: string;
  left_value?: string;
  right_label?: string;
  right_value?: string;
  comparison_status?: string;
  ref_filename?: string;
  ref_page?: number;
  ref_bbox?: number[];
  ref_highlights?: Array<{ page: number; bbox: number[] }>;
}

export interface FmuVariableData {
  name: string;
  causality: string;
  variability?: string;
  start?: string;
  unit?: string;
  description?: string;
}

export type LegacyCanvasNodeType =
  | "concept"
  | "topic"
  | "fact"
  | "spec"
  | "document"
  | "source"
  | "entity"
  | "category"
  | "fmu"
  | "plot"
  | "image"
  | "funnel"
  | "area";

export interface LegacyCanvasNode {
  id: string;
  node_type: LegacyCanvasNodeType;
  status?: NodeStatus;
  last_updated_run_id?: string;
  color?: string;
  title?: string;
  text?: string;
  spec_title?: string;
  properties?: SpecProperty[];
  parameter_sections?: ParameterSection[];
  filename?: string;
  page?: number;
  bbox?: number[];
  highlights?: Array<{ page: number; bbox: number[] }>;
  fmu_filename?: string;
  fmu_model_name?: string;
  fmu_variables?: FmuVariableData[];
  fmu_param_values?: Record<string, string>;
  image_filename?: string;
  image_page?: number;
  image_bbox?: number[];
  image_highlights?: string[];
  image_caption?: string;
  plot_job_id?: string;
  plot_fmu_filename?: string;
  plot_signal_names?: string[];
  plot_stop_time?: number;
  plot_param_values?: Record<string, number>;
  funnel_label?: string;
  area_label?: string;
  area_width?: number;
  area_height?: number;
  width?: number;
  height?: number;
  parent_id?: string;
}

export type CanvasItemKind =
  | "content"
  | "document"
  | "media"
  | "model"
  | "result"
  | "container";

export type CanvasItemRenderKind =
  | "treeLabel"
  | "markdownCard"
  | "specCard"
  | "sourceChip"
  | "documentCard"
  | "imageCard"
  | "fmuCard"
  | "plotCard"
  | "funnelChip"
  | "areaContainer";

export interface CanvasItemMetadata {
  legacy?: LegacyCanvasNode;
  document?: KBDocument;
  semanticType?: LegacyCanvasNodeType | "document";
  spec?: {
    title?: string;
    properties?: SpecProperty[];
  };
  evidence?: {
    filename?: string;
    page?: number;
    bbox?: number[];
    highlights?: Array<{ page: number; bbox: number[] }>;
  };
  fmu?: {
    filename?: string;
    modelName?: string;
    variables?: FmuVariableData[];
    paramValues?: Record<string, string>;
  };
  image?: {
    filename?: string;
    page?: number;
    bbox?: number[];
    highlights?: string[];
    caption?: string;
  };
  plot?: {
    jobId?: string;
    fmuFilename?: string;
    signalNames?: string[];
    stopTime?: number;
    paramValues?: Record<string, number>;
  };
  funnel?: {
    label?: string;
  };
  area?: {
    label?: string;
    width?: number;
    height?: number;
  };
}

export interface CanvasItem {
  id: string;
  kind: CanvasItemKind;
  renderKind: CanvasItemRenderKind;
  semanticType: LegacyCanvasNodeType | "document";
  status?: NodeStatus;
  color?: string;
  title?: string;
  text?: string;
  markdown?: string;
  parentId?: string;
  metadata?: CanvasItemMetadata;
  // Compatibility fields kept while we migrate existing renderers and views.
  node_type: LegacyCanvasNodeType | "document";
  spec_title?: string;
  properties?: SpecProperty[];
  parameter_sections?: ParameterSection[];
  filename?: string;
  page?: number;
  bbox?: number[];
  highlights?: Array<{ page: number; bbox: number[] }>;
  fmu_filename?: string;
  fmu_model_name?: string;
  fmu_variables?: FmuVariableData[];
  fmu_param_values?: Record<string, string>;
  image_filename?: string;
  image_page?: number;
  image_bbox?: number[];
  image_highlights?: string[];
  image_caption?: string;
  plot_job_id?: string;
  plot_fmu_filename?: string;
  plot_signal_names?: string[];
  plot_stop_time?: number;
  plot_param_values?: Record<string, number>;
  funnel_label?: string;
  area_label?: string;
  area_width?: number;
  area_height?: number;
  width?: number;
  height?: number;
  parent_id?: string;
  last_updated_run_id?: string;
}

function resolveCanvasItemKind(nodeType: LegacyCanvasNodeType): CanvasItemKind {
  if (nodeType === "document") return "document";
  if (nodeType === "fmu") return "model";
  if (nodeType === "plot") return "result";
  if (nodeType === "image") return "media";
  if (nodeType === "funnel" || nodeType === "area") return "container";
  return "content";
}

function resolveCanvasItemRenderKind(nodeType: LegacyCanvasNodeType): CanvasItemRenderKind {
  if (nodeType === "document") return "documentCard";
  if (nodeType === "fact") return "markdownCard";
  if (nodeType === "spec") return "specCard";
  if (nodeType === "source") return "sourceChip";
  if (nodeType === "image") return "imageCard";
  if (nodeType === "fmu") return "fmuCard";
  if (nodeType === "plot") return "plotCard";
  if (nodeType === "funnel") return "funnelChip";
  if (nodeType === "area") return "areaContainer";
  return "treeLabel";
}

export function adaptLegacyNodeToCanvasItem(node: LegacyCanvasNode): CanvasItem {
  return {
    id: node.id,
    kind: resolveCanvasItemKind(node.node_type),
    renderKind: resolveCanvasItemRenderKind(node.node_type),
    semanticType: node.node_type,
    status: node.status,
    color: node.color,
    title: node.title,
    text: node.text,
    markdown: node.text,
    parentId: node.parent_id,
    metadata: {
      legacy: node,
      semanticType: node.node_type,
      spec: {
        title: node.spec_title,
        properties: node.properties,
      },
      evidence: {
        filename: node.filename,
        page: node.page,
        bbox: node.bbox,
        highlights: node.highlights,
      },
      fmu: {
        filename: node.fmu_filename,
        modelName: node.fmu_model_name,
        variables: node.fmu_variables,
        paramValues: node.fmu_param_values,
      },
      image: {
        filename: node.image_filename,
        page: node.image_page,
        bbox: node.image_bbox,
        highlights: node.image_highlights,
        caption: node.image_caption,
      },
      plot: {
        jobId: node.plot_job_id,
        fmuFilename: node.plot_fmu_filename,
        signalNames: node.plot_signal_names,
        stopTime: node.plot_stop_time,
        paramValues: node.plot_param_values,
      },
      funnel: {
        label: node.funnel_label,
      },
      area: {
        label: node.area_label,
        width: node.area_width,
        height: node.area_height,
      },
    },
    node_type: node.node_type,
    spec_title: node.spec_title,
    properties: node.properties,
    parameter_sections: node.parameter_sections,
    filename: node.filename,
    page: node.page,
    bbox: node.bbox,
    highlights: node.highlights,
    fmu_filename: node.fmu_filename,
    fmu_model_name: node.fmu_model_name,
    fmu_variables: node.fmu_variables,
    fmu_param_values: node.fmu_param_values,
    image_filename: node.image_filename,
    image_page: node.image_page,
    image_bbox: node.image_bbox,
    image_highlights: node.image_highlights,
    image_caption: node.image_caption,
    plot_job_id: node.plot_job_id,
    plot_fmu_filename: node.plot_fmu_filename,
    plot_signal_names: node.plot_signal_names,
    plot_stop_time: node.plot_stop_time,
    plot_param_values: node.plot_param_values,
    funnel_label: node.funnel_label,
    area_label: node.area_label,
    area_width: node.area_width,
    area_height: node.area_height,
    width: node.width,
    height: node.height,
    parent_id: node.parent_id,
    last_updated_run_id: node.last_updated_run_id,
  };
}

export function adaptDocumentToCanvasItem(doc: KBDocument): CanvasItem {
  return {
    id: `__doc_${doc.document_id}`,
    kind: "document",
    renderKind: "documentCard",
    semanticType: "document",
    status: doc.status === "processing" || doc.status === "pending" ? "searching" : doc.status === "error" || doc.status === "failed" ? "not_found" : "found",
    color: "",
    title: doc.filename,
    text: "",
    markdown: "",
    parentId: undefined,
    metadata: {
      document: doc,
      semanticType: "document",
    },
    node_type: "document",
  };
}
