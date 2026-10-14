"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { type Phase, phaseAt } from "./incident-cycle";

// The demo shop as a living service graph. Every cycle checkout fails (red,
// errors flowing to its callers), OpsPilot rolls it back, and it recovers.

type Node = { id: string; position: [number, number, number]; size: number };

const NODES: Node[] = [
  { id: "storefront", position: [-3.2, 0.2, 0], size: 0.42 },
  { id: "checkout", position: [0, 0, 0.4], size: 0.55 },
  { id: "payment", position: [3, 1.5, -0.4], size: 0.38 },
  { id: "inventory", position: [3.3, -0.1, 0.6], size: 0.38 },
  { id: "notification", position: [2.8, -1.7, -0.3], size: 0.36 },
];
const EDGES: [string, string][] = [
  ["storefront", "checkout"],
  ["checkout", "payment"],
  ["checkout", "inventory"],
  ["checkout", "notification"],
];
// Faint satellites give depth without competing with the five services.
const SATELLITES = 140;
const PARTICLES_PER_EDGE = 6;

/** Colours come from the design tokens on <html>. */
function token(name: string): THREE.Color {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return new THREE.Color(value || "white");
}

function useTokens() {
  return useMemo(
    () => ({
      healthy: token("--status-healthy"),
      critical: token("--status-critical"),
      degraded: token("--status-degraded"),
      accent: token("--accent"),
      muted: token("--text-muted"),
    }),
    [],
  );
}

const position = (id: string) => new THREE.Vector3(...NODES.find((n) => n.id === id)!.position);

function nodeColor(id: string, phase: Phase, colors: ReturnType<typeof useTokens>) {
  if (id !== "checkout" && id !== "storefront") return colors.healthy;
  if (phase === "failing" || phase === "investigating") return id === "checkout" ? colors.critical : colors.degraded;
  if (phase === "remediating") return id === "checkout" ? colors.degraded : colors.healthy;
  return colors.healthy;
}

function Services({ reduced }: { reduced: boolean }) {
  const colors = useTokens();
  const meshes = useRef<(THREE.Mesh | null)[]>([]);
  const rings = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const phase = reduced ? "healthy" : phaseAt(performance.now() / 1000);
    NODES.forEach((node, i) => {
      const mesh = meshes.current[i];
      if (!mesh) return;
      const material = mesh.material as THREE.MeshStandardMaterial;
      const target = nodeColor(node.id, phase, colors);
      material.color.lerp(target, 0.15);
      material.emissive.lerp(target, 0.15);
      const failing = node.id === "checkout" && (phase === "failing" || phase === "investigating");
      material.emissiveIntensity = failing ? 0.55 + Math.sin(t * 6) * 0.25 : 0.3;
      if (!reduced) {
        mesh.rotation.y = t * 0.25 + i;
        mesh.position.y = node.position[1] + Math.sin(t * 0.8 + i * 1.7) * 0.08;
      }
    });
    if (rings.current) {
      const visible = phase === "investigating" || phase === "remediating";
      const material = rings.current.material as THREE.MeshBasicMaterial;
      material.opacity += ((visible ? 0.7 : 0) - material.opacity) * 0.08;
      rings.current.rotation.z = t * 1.4;
      const s = 1 + Math.sin(t * 3) * 0.06;
      rings.current.scale.set(s, s, s);
    }
  });

  return (
    <group>
      {NODES.map((node, i) => (
        <mesh
          key={node.id}
          position={node.position}
          ref={(m) => {
            meshes.current[i] = m;
          }}
        >
          <icosahedronGeometry args={[node.size, 1]} />
          <meshStandardMaterial
            flatShading
            roughness={0.35}
            metalness={0.15}
            color={colors.healthy}
            emissive={colors.healthy}
          />
        </mesh>
      ))}
      {/* The agents at work: an iris ring around checkout while it is investigated. */}
      <mesh ref={rings} position={NODES[1].position} rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[0.85, 0.02, 8, 64]} />
        <meshBasicMaterial color={colors.accent} transparent opacity={0} />
      </mesh>
    </group>
  );
}

function Edges() {
  const colors = useTokens();
  const geometry = useMemo(() => {
    const points = EDGES.flatMap(([a, b]) => [position(a), position(b)]);
    return new THREE.BufferGeometry().setFromPoints(points);
  }, []);
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={colors.muted} transparent opacity={0.45} />
    </lineSegments>
  );
}

/** Requests flowing along the edges; red while checkout returns errors. */
function Traffic({ reduced }: { reduced: boolean }) {
  const colors = useTokens();
  const mesh = useRef<THREE.InstancedMesh>(null);
  const count = EDGES.length * PARTICLES_PER_EDGE;
  const helper = useMemo(() => new THREE.Object3D(), []);
  const color = useMemo(() => new THREE.Color(), []);

  useFrame(({ clock }) => {
    const instances = mesh.current;
    if (!instances) return;
    const t = clock.getElapsedTime();
    const phase = reduced ? "healthy" : phaseAt(performance.now() / 1000);
    EDGES.forEach(([a, b], e) => {
      const from = position(a);
      const to = position(b);
      for (let i = 0; i < PARTICLES_PER_EDGE; i++) {
        const k = e * PARTICLES_PER_EDGE + i;
        const progress = reduced ? i / PARTICLES_PER_EDGE : (t * 0.35 + i / PARTICLES_PER_EDGE + e * 0.13) % 1;
        helper.position.lerpVectors(from, to, progress);
        helper.scale.setScalar(0.045 + Math.sin(progress * Math.PI) * 0.03);
        helper.updateMatrix();
        instances.setMatrixAt(k, helper.matrix);
        const erroring =
          (phase === "failing" || phase === "investigating") && (a === "checkout" || b === "checkout") && i % 2 === 0;
        instances.setColorAt(k, color.copy(erroring ? colors.critical : colors.accent));
      }
    });
    instances.instanceMatrix.needsUpdate = true;
    if (instances.instanceColor) instances.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 10, 10]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

function Satellites() {
  const colors = useTokens();
  const geometry = useMemo(() => {
    const random = mulberry32(7);
    const points = Array.from({ length: SATELLITES }, () => {
      const r = 5 + random() * 6;
      const theta = random() * Math.PI * 2;
      const phi = (random() - 0.5) * 1.2;
      return new THREE.Vector3(r * Math.cos(theta), r * Math.sin(phi) * 0.6, r * Math.sin(theta) - 4);
    });
    return new THREE.BufferGeometry().setFromPoints(points);
  }, []);
  return (
    <points geometry={geometry}>
      <pointsMaterial color={colors.accent} size={0.035} transparent opacity={0.55} sizeAttenuation />
    </points>
  );
}

/** A slow orbit plus a gentle parallax that follows the pointer. */
function Rig({ reduced }: { reduced: boolean }) {
  const { camera, pointer } = useThree();
  useFrame(({ clock }) => {
    const t = reduced ? 0 : clock.getElapsedTime();
    const x = Math.sin(t * 0.08) * 1.2 + pointer.x * 0.8;
    const y = 0.6 + pointer.y * 0.5;
    camera.position.lerp(new THREE.Vector3(x, y, 8.2), 0.04);
    camera.lookAt(0.3, 0, 0);
  });
  return null;
}

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let r = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

export default function HeroScene({ reduced }: { reduced: boolean }) {
  return (
    <Canvas
      camera={{ position: [0, 0.6, 8.2], fov: 42 }}
      dpr={[1, 1.75]}
      frameloop={reduced ? "demand" : "always"}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      aria-hidden
    >
      <ambientLight intensity={0.5} />
      <directionalLight position={[4, 6, 5]} intensity={1.4} />
      <pointLight position={[-4, -2, 3]} intensity={12} distance={12} color={token("--accent")} />
      <Rig reduced={reduced} />
      <Satellites />
      <Edges />
      <Traffic reduced={reduced} />
      <Services reduced={reduced} />
    </Canvas>
  );
}
