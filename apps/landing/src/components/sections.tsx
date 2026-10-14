"use client";

import { animate, motion, useInView, useMotionValue, useReducedMotion, useScroll, useTransform } from "motion/react";
import { type PointerEvent, type ReactNode, useEffect, useRef, useState } from "react";

import { asset, DOCS, RELEASES, REPO, THREAT_MODEL } from "./links";

const reveal = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-80px" },
  transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] as const },
};

function SectionHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <motion.div {...reveal} className="mx-auto max-w-2xl text-center">
      <p className="font-mono text-xs tracking-[0.2em] text-accent uppercase">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">{title}</h2>
      {children && <p className="mt-4 text-pretty text-fg-secondary">{children}</p>}
    </motion.div>
  );
}

// ── The incident loop ────────────────────────────────────────────────────────

const STEPS = [
  {
    time: "00:00",
    title: "A faulty release ships",
    body: "Checkout 1.4.2 starts failing half its requests; storefront feels it.",
    tone: "critical",
  },
  {
    time: "01:47",
    title: "One incident opens",
    body: "A sustained error-rate breach, with persistence, cooldown, and hysteresis: one incident, callers noted as affected.",
    tone: "critical",
  },
  {
    time: "02:05",
    title: "Agents investigate",
    body: "Triage, observability, deployments, runbooks, synthesis. Read-only tools; every claim cites evidence.",
    tone: "accent",
  },
  {
    time: "02:26",
    title: "A human approves",
    body: "The incident commander approves the exact proposal version. Policy and namespace allow-lists are checked again.",
    tone: "accent",
  },
  {
    time: "02:26",
    title: "Rollback runs once",
    body: "Idempotent, leased, audited. Only rollback, restart, bounded scale, or pause — never shell, never delete.",
    tone: "degraded",
  },
  {
    time: "05:39",
    title: "Recovery is verified",
    body: "Error rate and p95 against the pre-incident baseline. Resolved, and a blameless postmortem is drafted.",
    tone: "healthy",
  },
] as const;

const TONE: Record<string, string> = {
  critical: "bg-critical shadow-glow-critical",
  accent: "bg-accent shadow-glow-accent",
  degraded: "bg-degraded",
  healthy: "bg-healthy",
};

export function IncidentLoop() {
  const ref = useRef<HTMLOListElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 75%", "end 55%"] });
  const scaleY = useTransform(scrollYProgress, [0, 1], [0, 1]);

  return (
    <section id="loop" className="scroll-mt-20 px-6 py-28">
      <SectionHeading eyebrow="The incident loop" title="From fault to verified fix in under six minutes">
        Timestamps from a real run on the demo cluster with a local 7B model. Waits are the system working, not people.
      </SectionHeading>
      <ol ref={ref} className="relative mx-auto mt-16 max-w-3xl">
        <div aria-hidden className="absolute top-2 bottom-2 left-[5.25rem] w-px bg-border sm:left-[6.25rem]" />
        <motion.div
          aria-hidden
          style={{ scaleY }}
          className="absolute top-2 bottom-2 left-[5.25rem] w-px origin-top bg-gradient-to-b from-critical via-accent to-healthy sm:left-[6.25rem]"
        />
        {STEPS.map((step, i) => (
          <motion.li
            key={step.title}
            {...reveal}
            transition={{ ...reveal.transition, delay: i * 0.04 }}
            className="relative grid grid-cols-[4.5rem_1.5rem_1fr] gap-x-3 pb-10 last:pb-0 sm:grid-cols-[5.5rem_1.5rem_1fr]"
          >
            <span className="pt-0.5 text-right font-mono text-sm text-fg-muted">{step.time}</span>
            <span className={`relative top-1.5 mx-auto size-3 rounded-full ${TONE[step.tone]}`} />
            <div>
              <h3 className="font-medium">{step.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-fg-secondary">{step.body}</p>
            </div>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}

// ── Features (bento) ─────────────────────────────────────────────────────────

function Spotlight({ className = "", children }: { className?: string; children: ReactNode }) {
  // Spotlight position plus a few degrees of tilt toward the pointer.
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    el.style.setProperty("--x", `${x}px`);
    el.style.setProperty("--y", `${y}px`);
    el.style.setProperty("--rx", `${((rect.height / 2 - y) / rect.height) * 6}deg`);
    el.style.setProperty("--ry", `${((x - rect.width / 2) / rect.width) * 6}deg`);
  };
  const onLeave = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.style.setProperty("--rx", "0deg");
    e.currentTarget.style.setProperty("--ry", "0deg");
  };
  return (
    <motion.div
      {...reveal}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      className={`spotlight tilt rounded-lg border border-border p-6 ${className}`}
    >
      <span aria-hidden className="border-trail" />
      {children}
    </motion.div>
  );
}

const FEATURES = [
  {
    title: "Evidence or it didn't happen",
    body: "Hypotheses and summary claims must cite collected evidence. Uncited claims are dropped or marked unverified — and without evidence, nothing is proposed.",
    tag: "Agent safety",
    wide: true,
  },
  {
    title: "Detection that doesn't flap",
    body: "Persistence, cooldown, and hysteresis on real Prometheus data. One incident per failure.",
    tag: "Detection",
  },
  {
    title: "Runbooks as context, not commands",
    body: "Retrieved text is untrusted; prompt injection is flagged and evaluated.",
    tag: "RAG",
  },
  {
    title: "Human-approved remediation",
    body: "Approval binds to the exact proposal version. Executed once, re-checked first.",
    tag: "Safety",
  },
  {
    title: "ML in shadow mode",
    body: "An Isolation Forest scored against a statistical baseline — and honestly left unpromoted.",
    tag: "ML",
  },
  {
    title: "Production-hardened",
    body: "Rate limits, CSP, idempotency everywhere, alerts with runbooks, chaos and load tests, nightly backups with a measured restore, signed images verified at admission.",
    tag: "Operations",
    full: true,
  },
];

export function Features() {
  return (
    <section id="features" className="scroll-mt-20 px-6 py-28">
      <SectionHeading eyebrow="What it does" title="An SRE teammate with guardrails built in" />
      <div className="mx-auto mt-14 grid max-w-6xl gap-4 md:grid-cols-3">
        {FEATURES.map((f) => (
          <Spotlight key={f.title} className={"full" in f ? "md:col-span-3" : "wide" in f ? "md:col-span-2" : ""}>
            <p className="font-mono text-[11px] tracking-[0.18em] text-accent uppercase">{f.tag}</p>
            <h3 className="mt-3 text-lg font-medium">{f.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-fg-secondary">{f.body}</p>
          </Spotlight>
        ))}
      </div>
    </section>
  );
}

// ── Metrics ──────────────────────────────────────────────────────────────────

function Counter({ to, decimals = 0, suffix = "" }: { to: number; decimals?: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduced = useReducedMotion();
  const value = useMotionValue(0);
  const [text, setText] = useState((0).toFixed(decimals));
  useEffect(() => {
    if (!inView) return;
    if (reduced) {
      value.set(to);
      return;
    }
    const controls = animate(value, to, { duration: 1.4, ease: [0.16, 1, 0.3, 1] });
    return () => controls.stop();
  }, [inView, reduced, to, value]);
  useEffect(() => value.on("change", (v) => setText(v.toFixed(decimals))), [value, decimals]);
  return (
    <span ref={ref}>
      {reduced ? to.toFixed(decimals) : text}
      {suffix}
    </span>
  );
}

const METRICS = [
  { to: 102, suffix: " ms", label: "p95 reads at 50 req/s", note: "target 300 ms" },
  { to: 31, suffix: " ms", label: "p95 writes at 20 req/s", note: "target 500 ms" },
  { to: 0, label: "unsafe proposals in evals", note: "incl. prompt injection" },
  { to: 6.8, decimals: 1, suffix: " s", label: "measured restore (RTO)", note: "target 4 h" },
  { to: 9, label: "chaos scenarios passing", note: "3 real bugs found & fixed" },
  { to: 100, label: "Lighthouse performance & a11y", note: "measured pages" },
];

export function Metrics() {
  return (
    <section className="px-6 py-24">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-3">
        {METRICS.map((m) => (
          <div key={m.label} className="bg-surface-1 p-6 sm:p-8">
            <p className="font-mono text-3xl tracking-tight sm:text-4xl">
              <Counter to={m.to} decimals={m.decimals} suffix={m.suffix} />
            </p>
            <p className="mt-2 text-sm text-fg-secondary">{m.label}</p>
            <p className="mt-0.5 text-xs text-fg-muted">{m.note}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ── Showcase: screenshots in a frame that straightens as it scrolls in ───────

const SHOTS = [
  {
    src: "/media/investigation.png",
    alt: "Agent investigation with a grounded rollback proposal awaiting approval",
    label: "Investigation",
  },
  { src: "/media/topology-focus.png", alt: "3D service topology focused on Checkout", label: "Topology" },
  {
    src: "/media/evaluations.png",
    alt: "Evaluations dashboard: agent success, detection delay, approval rate, cost",
    label: "Evaluations",
  },
  { src: "/media/ml-detector.png", alt: "ML detector in shadow mode compared with the baseline", label: "ML detector" },
];

export function Showcase() {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "center center"] });
  const rotateX = useTransform(scrollYProgress, [0, 1], reduced ? [0, 0] : [24, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], reduced ? [1, 1] : [0.9, 1]);
  const [active, setActive] = useState(0);

  return (
    <section id="product" className="scroll-mt-20 px-6 py-28">
      <SectionHeading eyebrow="The product" title="Built for the 3 a.m. page">
        A depth-layered interface with a command palette, live timelines, and a 3D map that flies to the failing
        service.
      </SectionHeading>
      <div className="mx-auto mt-10 flex max-w-6xl justify-center gap-2" role="tablist" aria-label="Screens">
        {SHOTS.map((shot, i) => (
          <button
            key={shot.label}
            role="tab"
            aria-selected={active === i}
            onClick={() => setActive(i)}
            className="relative rounded-full px-4 py-1.5 text-sm text-fg-secondary transition-colors hover:text-fg aria-selected:text-fg"
          >
            {active === i && (
              <motion.span
                layoutId="shot-pill"
                className="absolute inset-0 -z-10 rounded-full border border-border-strong bg-surface-2"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            {shot.label}
          </button>
        ))}
      </div>
      <div ref={ref} className="mx-auto mt-8 max-w-6xl [perspective:1400px]">
        <motion.div
          style={{ rotateX, scale }}
          className="overflow-hidden rounded-lg border border-border-strong bg-surface-1 shadow-3 shadow-glow-accent"
        >
          <div className="flex h-9 items-center gap-1.5 border-b border-border px-4">
            {["bg-critical", "bg-degraded", "bg-healthy"].map((c) => (
              <span key={c} className={`size-2.5 rounded-full ${c} opacity-70`} />
            ))}
            <span className="ml-3 font-mono text-xs text-fg-muted">opspilot · {SHOTS[active].label.toLowerCase()}</span>
          </div>
          <motion.img
            key={SHOTS[active].src}
            src={asset(SHOTS[active].src)}
            alt={SHOTS[active].alt}
            width={1440}
            height={900}
            loading="lazy"
            initial={reduced ? false : { opacity: 0, scale: 1.02 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5 }}
            className="block h-auto w-full"
          />
        </motion.div>
      </div>
    </section>
  );
}

// ── Stack marquee, architecture, call to action, footer ─────────────────────

const STACK = [
  "Next.js 16",
  "React 19",
  "React Three Fiber",
  "FastAPI",
  "LangGraph",
  "PostgreSQL + pgvector",
  "Redpanda",
  "Prometheus",
  "Loki",
  "Tempo",
  "OpenTelemetry",
  "scikit-learn",
  "MLflow",
  "Kubernetes",
  "Argo CD",
  "Argo Rollouts",
  "Terraform",
  "Karpenter",
  "cosign",
  "Kyverno",
];

export function Stack() {
  return (
    <section aria-label="Technology" className="py-12">
      <div className="marquee overflow-hidden">
        <ul className="marquee-track flex w-max gap-3">
          {[...STACK, ...STACK].map((item, i) => (
            <li
              key={`${item}-${i}`}
              aria-hidden={i >= STACK.length}
              className="rounded-full border border-border bg-surface-1/70 px-4 py-2 font-mono text-sm whitespace-nowrap text-fg-secondary"
            >
              {item}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function CallToAction() {
  return (
    <section className="px-6 py-28">
      <motion.div
        {...reveal}
        className="spotlight relative mx-auto max-w-4xl overflow-hidden rounded-lg border border-border px-8 py-14 text-center"
      >
        <span aria-hidden className="border-trail opacity-100" />
        <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          Run the whole loop on your laptop
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-fg-secondary">
          A kind cluster, the demo shop, the observability stack, and a local model. One command to start, one to break
          checkout.
        </p>
        <pre className="mx-auto mt-8 max-w-md overflow-x-auto rounded-sm border border-border bg-background/80 p-4 text-left font-mono text-sm text-fg-secondary">
          <code>{`make install && make dev
make deploy-local && make llm-up
make inject-failure SCENARIO=checkout-http-500`}</code>
        </pre>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <a
            href={REPO}
            className="inline-flex h-11 items-center rounded-sm bg-accent px-5 font-medium text-on-accent transition-colors hover:bg-accent-hover"
          >
            Get the code
          </a>
          <a
            href={RELEASES}
            className="inline-flex h-11 items-center rounded-sm border border-border-strong px-5 font-medium transition-colors hover:bg-surface-2"
          >
            Watch the walkthrough
          </a>
        </div>
      </motion.div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-border px-6 py-10">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 text-sm text-fg-muted">
        <p>OpsPilot · MIT licensed</p>
        <nav aria-label="Footer" className="flex flex-wrap gap-5">
          <a className="hover:text-fg" href={REPO}>
            GitHub
          </a>
          <a className="hover:text-fg" href={DOCS}>
            Docs
          </a>
          <a className="hover:text-fg" href={THREAT_MODEL}>
            Threat model
          </a>
          <a className="hover:text-fg" href={RELEASES}>
            Releases
          </a>
        </nav>
      </div>
    </footer>
  );
}
