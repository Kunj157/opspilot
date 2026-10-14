"use client";

import { AdaptiveDpr, Html, Line, OrbitControls, PerformanceMonitor } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import { AdditiveBlending, CanvasTexture, type Group, type Mesh, type Sprite, Vector3 } from "three";

import { useVisible } from "@/lib/use-page-visible";
import { useReducedMotion } from "@/lib/use-reduced-motion";

import type { Topology } from "./model";
import {
  type CameraPose,
  flowingEdges,
  focusOn,
  glows,
  overview,
  type SceneEdge,
  type SceneNode,
  type Shape,
  toScene,
} from "./scene";
import { describeNode } from "./service-topology-2d";

type Palette = Record<"healthy" | "degraded" | "critical" | "unknown" | "accent" | "edge" | "node" | "fog", string>;

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
    fog: token("surface-1"),
  };
}

/** A soft round light, drawn once and tinted per sprite; additive blending makes it read as bloom. */
function haloTexture(): CanvasTexture {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(255,255,255,0.9)");
  gradient.addColorStop(0.35, "rgba(255,255,255,0.35)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  return new CanvasTexture(canvas);
}

/** Bloom-like halo behind a service in trouble; breathes slowly unless motion is reduced. */
function Halo({ color, texture, animate }: { color: string; texture: CanvasTexture; animate: boolean }) {
  const sprite = useRef<Sprite>(null);
  useFrame(({ clock }) => {
    if (!sprite.current) return;
    const s = animate ? 1.5 + 0.15 * Math.sin(clock.elapsedTime * 1.6) : 1.5;
    sprite.current.scale.set(s, s, 1);
  });
  return (
    <sprite ref={sprite} scale={[1.5, 1.5, 1]}>
      <spriteMaterial
        map={texture}
        color={color}
        blending={AdditiveBlending}
        transparent
        depthWrite={false}
        opacity={0.55}
      />
    </sprite>
  );
}

const PARTICLES_PER_EDGE = 3;

/** Small lights travelling from caller to callee along a flowing edge. */
function FlowParticles({ edge, color }: { edge: SceneEdge; color: string }) {
  const group = useRef<Group>(null);
  const from = useMemo(() => new Vector3(...edge.from), [edge.from]);
  const to = useMemo(() => new Vector3(...edge.to), [edge.to]);
  useFrame(({ clock }) => {
    group.current?.children.forEach((child, i) => {
      const t = (clock.elapsedTime * 0.35 + i / PARTICLES_PER_EDGE) % 1;
      child.position.lerpVectors(from, to, t);
      child.scale.setScalar(Math.sin(t * Math.PI));
    });
  });
  return (
    <group ref={group}>
      {Array.from({ length: PARTICLES_PER_EDGE }, (_, i) => (
        <mesh key={i}>
          <sphereGeometry args={[0.045, 8, 8]} />
          <meshBasicMaterial color={color} transparent opacity={0.9} />
        </mesh>
      ))}
    </group>
  );
}

const ARRIVED = 0.01;

/** The part of drei's OrbitControls the rig drives. */
type OrbitControlsImpl = { target: Vector3; update: () => void };

/**
 * Flies the camera to a pose with an exponential ease, then lets go so the user
 * can orbit freely. Reduced motion jumps straight there.
 */
function CameraRig({
  pose,
  poseKey,
  reduced,
  onArrive,
}: {
  pose: CameraPose;
  poseKey: string;
  reduced: boolean;
  onArrive: (key: string) => void;
}) {
  const { camera, controls, invalidate } = useThree();
  const flying = useRef(false);
  const goal = useMemo(
    () => ({ target: new Vector3(...pose.target), position: new Vector3(...pose.position) }),
    [pose],
  );

  useEffect(() => {
    const orbit = controls as OrbitControlsImpl | null;
    if (!orbit) return;
    if (reduced) {
      camera.position.copy(goal.position);
      orbit.target.copy(goal.target);
      orbit.update();
      invalidate();
      onArrive(poseKey);
      return;
    }
    flying.current = true;
    invalidate();
  }, [goal, poseKey, reduced, camera, controls, invalidate, onArrive]);

  useFrame((_, delta) => {
    const orbit = controls as OrbitControlsImpl | null;
    if (!flying.current || !orbit) return;
    const k = 1 - Math.exp(-delta * 4.5);
    camera.position.lerp(goal.position, k);
    orbit.target.lerp(goal.target, k);
    orbit.update();
    if (camera.position.distanceTo(goal.position) < ARRIVED && orbit.target.distanceTo(goal.target) < ARRIVED) {
      flying.current = false;
      onArrive(poseKey);
    }
  });
  return null;
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
  halo,
  selected,
  dimmed,
  animate,
  onSelect,
  onOpen,
}: {
  item: SceneNode;
  palette: Palette;
  halo: CanvasTexture;
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

  const glow = glows(node);
  return (
    <group position={item.position}>
      {glow && !dimmed && <Halo color={palette[glow]} texture={halo} animate={animate} />}
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
  const [halo] = useState(haloTexture);
  const { distance } = scene;
  const frameloop = !visible ? "never" : reduced ? "demand" : "always";
  const connected = (id: string) => id === selectedId;
  const focused = scene.nodes.find((n) => n.id === selectedId);
  const pose = useMemo(() => (focused ? focusOn(focused, distance) : overview(distance)), [focused, distance]);
  const poseKey = focused?.id ?? "overview";
  // Which pose the camera has reached; tests and the reset control read it.
  const [arrived, setArrived] = useState<string | null>(null);
  const flowing = flowingEdges(scene.edges, selectedId);

  return (
    <div
      ref={wrapper}
      data-testid="topology-3d"
      data-frameloop={frameloop}
      data-camera-target={arrived ?? undefined}
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
        <fog attach="fog" args={[palette.fog, distance * 0.9, distance * 2.2]} />
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
        {!reduced &&
          flowing.map((edge) => (
            <FlowParticles key={edge.id} edge={edge} color={edge.failing ? palette.critical : palette.accent} />
          ))}
        {scene.nodes.map((item) => (
          <Node
            key={item.id}
            item={item}
            palette={palette}
            halo={halo}
            selected={item.id === selectedId}
            dimmed={Boolean(selectedId) && item.id !== selectedId}
            animate={!reduced}
            onSelect={onSelect}
            onOpen={onOpen}
          />
        ))}
        <OrbitControls
          makeDefault
          enablePan={false}
          enableDamping={!reduced}
          minDistance={distance * 0.5}
          maxDistance={distance * 1.6}
          minPolarAngle={Math.PI * 0.3}
          maxPolarAngle={Math.PI * 0.7}
          minAzimuthAngle={-Math.PI / 4}
          maxAzimuthAngle={Math.PI / 4}
        />
        <CameraRig pose={pose} poseKey={poseKey} reduced={reduced} onArrive={setArrived} />
      </Canvas>
    </div>
  );
}
