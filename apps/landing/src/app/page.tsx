import { Hero } from "@/components/hero";
import { Nav } from "@/components/nav";
import { CallToAction, Features, Footer, IncidentLoop, Metrics, Showcase, Stack } from "@/components/sections";

export default function Home() {
  return (
    <>
      <a
        href="#main"
        className="sr-only z-[60] rounded-sm bg-accent px-3 py-2 text-on-accent focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <Nav />
      <main id="main">
        <Hero />
        <Stack />
        <IncidentLoop />
        <Features />
        <Metrics />
        <Showcase />
        <CallToAction />
      </main>
      <Footer />
    </>
  );
}
