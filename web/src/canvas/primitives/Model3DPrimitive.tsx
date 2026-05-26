import { Suspense, useEffect, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Canvas, useLoader } from "@react-three/fiber";
import { OrbitControls, Bounds } from "@react-three/drei";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import * as THREE from "three";

import { cad, type CadModel } from "@/api/cad";

/**
 * Model3DPrimitive — a 3D viewport node showing a CAD model.
 *
 * Reads `data.cad_slug`, fetches the CadModel summary for label/parameter
 * counts, and mounts a small three.js canvas streaming the raw model
 * bytes from /api/cad/{slug}/model. STL / OBJ / glTF supported via the
 * three.js example loaders. STEP / parametric formats fall back to a
 * card with the geometry stats.
 *
 * Loader picked from data.kind (or the model's `kind` field, fetched
 * lazily). The viewport itself uses OrbitControls so users can spin /
 * zoom inside the node — left-drag rotates, right-drag pans, scroll zooms.
 */
type CadNodeData = {
  label?: string;
  cad_slug?: string;
  kind?: string;
  parameters?: string[];
  view_state?: Record<string, number | string | boolean>;
  dashed?: boolean;
};

const VIEWPORT_KINDS = new Set(["stl", "obj", "gltf", "glb"]);

export function Model3DPrimitive({ data }: NodeProps) {
  const d = data as CadNodeData;
  const slug = d.cad_slug;
  const [model, setModel] = useState<CadModel | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    cad.get(slug)
      .then((m) => { if (!cancelled) setModel(m); })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [slug]);

  const kind = (d.kind ?? model?.kind ?? "unknown").toLowerCase();
  const canRender3D = slug && VIEWPORT_KINDS.has(kind);
  const url = slug && canRender3D ? cad.modelUrl(slug) : null;
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";

  return (
    <div className={`w-72 rounded-lg border ${borderStyle} border-neutral-400 bg-white text-sm shadow-sm`}>
      <Handle type="target" position={Position.Left} />

      <div className="flex items-center justify-between border-b border-neutral-200 px-3 py-2 gap-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">
            cad · {kind}
          </div>
          <div className="truncate font-medium text-neutral-900">
            {d.label ?? model?.title ?? model?.filename ?? slug ?? "model"}
          </div>
        </div>
        {model?.parameters?.length ? (
          <span
            className="shrink-0 rounded border border-emerald-300 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700"
            title={`${model.parameters.length} parameters`}
          >
            {model.parameters.length}p
          </span>
        ) : null}
      </div>

      <div className="h-48 w-full bg-neutral-100">
        {url ? (
          <Canvas camera={{ position: [3, 3, 3], fov: 45 }} dpr={[1, 2]}>
            <ambientLight intensity={0.4} />
            <directionalLight position={[5, 5, 5]} intensity={0.8} />
            <Suspense fallback={null}>
              <Bounds fit clip observe margin={1.2}>
                <ModelMesh url={url} kind={kind} />
              </Bounds>
            </Suspense>
            <OrbitControls makeDefault enableDamping dampingFactor={0.1} />
          </Canvas>
        ) : (
          <div className="flex h-full items-center justify-center px-3 text-center text-xs text-neutral-500">
            {error
              ? `failed to load: ${error}`
              : kind === "step" || kind === "iges"
                ? `${kind.toUpperCase()} not yet rendered (parser pending)`
                : "no 3D viewport for this kind"}
          </div>
        )}
      </div>

      {model?.geometry ? (
        <div className="grid grid-cols-2 gap-1 border-t border-neutral-200 px-3 py-2 text-[10px] text-neutral-500">
          {model.geometry.triangle_count != null ? (
            <div><span className="text-neutral-400">tris</span> {model.geometry.triangle_count.toLocaleString()}</div>
          ) : null}
          {model.geometry.vertex_count != null ? (
            <div><span className="text-neutral-400">verts</span> {model.geometry.vertex_count.toLocaleString()}</div>
          ) : null}
          {model.geometry.units ? (
            <div><span className="text-neutral-400">units</span> {model.geometry.units}</div>
          ) : null}
          {model.geometry.bounding_box ? (
            <div className="col-span-2">
              <span className="text-neutral-400">bbox</span>{" "}
              {model.geometry.bounding_box
                .map((v) => v.toFixed(1))
                .reduce<[string[], string[]]>(
                  (acc, v, i) => (i < 3 ? (acc[0].push(v), acc) : (acc[1].push(v), acc)),
                  [[], []],
                )
                .map((p) => `(${p.join(", ")})`)
                .join(" → ")}
            </div>
          ) : null}
        </div>
      ) : null}

      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function ModelMesh({ url, kind }: { url: string; kind: string }) {
  if (kind === "stl") {
    return <StlMesh url={url} />;
  }
  if (kind === "obj") {
    return <ObjMesh url={url} />;
  }
  if (kind === "gltf" || kind === "glb") {
    return <GltfMesh url={url} />;
  }
  return null;
}

function StlMesh({ url }: { url: string }) {
  const geometry = useLoader(STLLoader, url);
  return (
    <mesh geometry={geometry as unknown as THREE.BufferGeometry} castShadow receiveShadow>
      <meshStandardMaterial color="#9CA3AF" metalness={0.1} roughness={0.6} />
    </mesh>
  );
}

function ObjMesh({ url }: { url: string }) {
  const obj = useLoader(OBJLoader, url);
  return <primitive object={obj} />;
}

function GltfMesh({ url }: { url: string }) {
  const gltf = useLoader(GLTFLoader, url);
  return <primitive object={gltf.scene} />;
}
