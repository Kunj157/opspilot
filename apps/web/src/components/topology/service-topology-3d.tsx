"use client";

import { AdaptiveDpr, Html, Line, OrbitControls, PerformanceMonitor } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import type { Mesh } from "three";

import { useVisible } from "@/lib/use-page-visible";
import { useReducedMotion } from "@/lib/use-reduced-motion";

import type { Topology } from "./model";
import { type SceneNode, type Shape, toScene } from "./scene";
import { describeNode } from "./service-topology-2d";

type Palette = Record<"healthy" | "degraded" | "critical" | "unknown" | "accent" | "edge" | "node", string>;

/** Scene colours come from the CSS tokens, so the 3D view matches the rest of the UI. */
function readPalette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const token = (name: string) => css.getPropertyValue(`--${name}`).trim();
  return {
    healthy: token("status-healthy"),
    degraded: token("status-degraded"),
    critical: token("status-critical"),
    unknown: token("status-unknown"),
    accent: token("accent"),
    edge: token("text-muted"),
    node: token("surface-3"),
  };
}

function Geometry({ shape }: { shape: Shape }) {
  // Low-poly on purpose: a handful of faces per node.
  switch (shape) {
    case "cone":
      return <coneGeometry args={[0.32, 0.55, 3]} />;
    case "box":
      return <boxGeometry args={[0.46, 0.46, 0.46]} />;
    case "octahedron":
      return <octahedronGeometry args={[0.32, 0]} />;
    default:
      return <icosahedronGeometry args={[0.3, 1]} />;
  }
}

function Node({
  item,
  palette,
  selected,
  dimmed,
  animate,
  onSelect,
  onOpen,
}: {
  item: SceneNode;
  palette: Palette;
  selected: boolean;
  dimmed: boolean;
  animate: boolean;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
}) {
  const [hovered, setHovered] = useState(false);
  const pulse = useRef<Mesh>(null);
  const { node } = item;

  useFrame(({ clock }) => {
    if (!pulse.current) return;
    const s = animate ? 1 + 0.12 * Math.sin(clock.elapsedTime * 2.4) : 1;
    pulse.current.scale.setScalar(s);
  });

  return (
    <group position={item.position}>
      <mesh
        onClick={(e) => {
          e.stopPropagation();
          onSelect(node.id);
        }}
        onDoubleClick={(e) => {
          e.stopPropagation();
          onOpen(node.id);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHovered(true);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          setHovered(false);
          document.body.style.cursor = "";
        }}
      >
        <Geometry shape={item.shape} />
        <meshStandardMaterial
          color={palette[node.health_status]}
          flatShading
          wireframe={node.health_status === "unknown"}
          transparent
          opacity={dimmed ? 0.35 : 1}
          emissive={palette[node.health_status]}
          emissiveIntensity={selected || hovered ? 0.35 : 0.08}
        />
      </mesh>
      {(selected || hovered) && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.48, 0.02, 6, 32]} />
          <meshBasicMaterial color={palette.accent} />
        </mesh>
      )}
      {node.investigating && (
        <mesh ref={pulse}>
          <torusGeometry args={[0.6, 0.015, 6, 40]} />
          <meshBasicMaterial color={palette.accent} transparent opacity={0.8} />
        </mesh>
      )}
      {(selected || hovered) && (
        <Html center position={[0, -0.62, 0]} className="pointer-events-none">
          <span className="rounded-sm border border-border bg-surface-glass px-2 py-1 text-xs whitespace-nowrap text-fg shadow-2 backdrop-blur-sm">
            {describeNode(node)}
          </span>
        </Html>
      )}
    </group>
  );
}

/**
 * Signature 3D topology (§16.3). Rendered only on the client, loaded lazily,
 * and never the only way to reach anything: the 2D map and details panel
 * offer every action.
 */
export default function ServiceTopology3D({
  topology,
  selectedId,
  onSelect,
  onOpen,
  onContextLost,
}: {
  topology: Topology;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
  onContextLost: () => void;
}) {
  const wrapper = useRef<HTMLDivElement>(null);
  const visible = useVisible(wrapper);
  const reduced = useReducedMotion();
  const [palette] = useState(readPalette);
  const [dpr, setDpr] = useState(1.5);
  const scene = useMemo(() => toScene(topology), [topology]);
  const { distance } = scene;
  const frameloop = !visible ? "never" : reduced ? "demand" : "always";
  const connected = (id: string) => id === selectedId;

  return (
    <div
      ref={wrapper}
      data-testid="topology-3d"
      data-frameloop={frameloop}
      aria-hidden
      className="h-[22rem] w-full overflow-hidden rounded-card bg-surface-1"
    >
      <Canvas
        frameloop={frameloop}
        dpr={[1, dpr]}
        camera={{ position: [0, 0, distance], fov: 45 }}
        gl={{ antialias: true, powerPreference: "low-power" }}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener("webglcontextlost", onContextLost, { once: true });
        }}
        onPointerMissed={() => document.body.style.removeProperty("cursor")}
      >
        <PerformanceMonitor onDecline={() => setDpr(1)} />
        <AdaptiveDpr pixelated />
        <ambientLight intensity={0.6} />
        <directionalLight position={[3, 4, 6]} intensity={1.1} />
        {scene.edges.map((edge) => {
          const highlighted = connected(edge.sourceId) || connected(edge.targetId);
          return (
            <Line
              key={edge.id}
              points={[edge.from, edge.to]}
              color={edge.failing ? palette.critical : palette.edge}
              lineWidth={highlighted ? 2.5 : 1.2}
              transparent
              opacity={selectedId && !highlighted ? 0.25 : 0.9}
            />
          );
        })}
        {scene.nodes.map((item) => (
          <Node
            key={item.id}
            item={item}
            palette={palette}
            selected={item.id === selectedId}
            dimmed={Boolean(selectedId) && item.id !== selectedId}
            animate={!reduced}
            onSelect={onSelect}
            onOpen={onOpen}
          />
        ))}
        <OrbitControls
          enablePan={false}
          enableDamping={!reduced}
          minDistance={distance * 0.5}
          maxDistance={distance * 1.6}
          minPolarAngle={Math.PI * 0.3}
          maxPolarAngle={Math.PI * 0.7}
          minAzimuthAngle={-Math.PI / 4}
          maxAzimuthAngle={Math.PI / 4}
        />
      </Canvas>
    </div>
  );
}
