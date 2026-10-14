"use client";

import { motion, useReducedMotion } from "motion/react";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import { PHASES, phaseIndexAt } from "./incident-cycle";
import { REPO } from "./links";

// The 3D scene loads after the page is interactive and never blocks the headline.
const HeroScene = dynamic(() => import("./hero-scene"), { ssr: false });

function canUseWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

const DOT: Record<string, string> = {
  healthy: "bg-healthy",
  failing: "bg-critical",
  investigating: "bg-accent",
  remediating: "bg-degraded",
  recovered: "bg-healthy",
};

function LiveCaption({ reduced }: { reduced: boolean }) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => setIndex(phaseIndexAt(performance.now() / 1000)), 250);
    return () => clearInterval(id);
  }, [reduced]);
  const current = PHASES[index];
  return (
    <div
      role="status"
      aria-live="off"
      className="inline-flex items-center gap-2.5 rounded-full border border-border bg-surface-glass px-3.5 py-1.5 text-xs text-fg-secondary backdrop-blur"
    >
      <span className={`size-2 rounded-full ${DOT[current.phase]} transition-colors duration-500`} />
      <motion.span key={current.phase} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}>
        {current.caption}
      </motion.span>
    </div>
  );
}

const rise = {
  hidden: { opacity: 0, y: 18, filter: "blur(6px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)" },
};

export function Hero() {
  const reduced = Boolean(useReducedMotion());
  const [webgl, setWebgl] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- WebGL can only be probed in the browser
    setWebgl(canUseWebGL());
  }, []);

  return (
    <section className="relative isolate overflow-hidden pt-28 pb-16 sm:pt-36">
      <div aria-hidden className="horizon-grid absolute inset-x-[-20%] top-[78%] -z-10 h-[60%]" />
      <div className="mx-auto grid max-w-7xl items-center gap-10 px-6 lg:grid-cols-[1.05fr_1fr]">
        <motion.div
          initial="hidden"
          animate="show"
          transition={{ staggerChildren: 0.09, delayChildren: 0.05 }}
          className="relative z-10"
        >
          <motion.p
            variants={rise}
            className="mb-5 inline-flex items-center gap-2 rounded-full border border-border bg-surface-1/70 px-3 py-1 font-mono text-xs tracking-wide text-accent"
          >
            <span className="size-1.5 rounded-full bg-accent shadow-glow-accent" /> AI-assisted SRE · open source
          </motion.p>
          <motion.h1
            variants={rise}
            className="text-[2.6rem] leading-[1.05] font-semibold tracking-tight text-balance sm:text-6xl"
          >
            Incidents, investigated by agents.
            <br />
            <span className="text-sheen">Fixed only when you say so.</span>
          </motion.h1>
          <motion.p variants={rise} className="mt-6 max-w-xl text-lg leading-relaxed text-pretty text-fg-secondary">
            OpsPilot detects incidents in your Kubernetes services, investigates them with evidence-citing AI agents and
            machine learning, proposes a safe rollback, runs it after a human approves, verifies recovery, and writes
            the postmortem.
          </motion.p>
          <motion.div variants={rise} className="mt-9 flex flex-wrap items-center gap-3">
            <a
              href={REPO}
              className="group inline-flex h-11 items-center gap-2 rounded-sm bg-accent px-5 font-medium text-on-accent shadow-glow-accent transition-colors hover:bg-accent-hover"
            >
              View on GitHub
              <span aria-hidden className="transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </a>
            <a
              href="#loop"
              className="inline-flex h-11 items-center rounded-sm border border-border-strong bg-surface-1/60 px-5 font-medium text-fg backdrop-blur transition-colors hover:bg-surface-2"
            >
              See the incident loop
            </a>
          </motion.div>
          <motion.dl variants={rise} className="mt-10 flex flex-wrap gap-x-8 gap-y-3 text-sm text-fg-muted">
            {[
              ["~90 s", "fault to incident"],
              ["~15 s", "agent investigation"],
              ["3 min", "approve to verified"],
            ].map(([value, label]) => (
              <div key={label} className="flex items-baseline gap-2">
                <dt className="font-mono text-base text-fg">{value}</dt>
                <dd>{label}</dd>
              </div>
            ))}
          </motion.dl>
        </motion.div>

        <div className="relative">
          <div className="relative aspect-[5/4] w-full">
            {webgl ? (
              <HeroScene reduced={reduced} />
            ) : (
              <div className="grid h-full place-items-center rounded-lg border border-border bg-surface-1/50 text-sm text-fg-muted">
                Storefront → Checkout → Payment · Inventory · Notification
              </div>
            )}
          </div>
          <div className="absolute inset-x-0 bottom-2 flex justify-center">
            <LiveCaption reduced={reduced} />
          </div>
        </div>
      </div>
    </section>
  );
}
