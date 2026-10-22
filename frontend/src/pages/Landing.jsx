import { useEffect, useRef, useState } from "react";
import { BadgeCheck } from "lucide-react";
import { CONTENT } from "@/content";
import { trackPageView } from "@/lib/tracking";
import { CtaButton, useJoin } from "@/components/CtaButton";
import { Benefits, Steps } from "@/components/Sections";
import { CompoundingCard, GiveawayCard } from "@/components/HighlightCards";

const useNoneVisible = (refs) => {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    const seen = new Map();
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => seen.set(e.target, e.isIntersecting));
      setHidden([...seen.values()].every((v) => !v));
    });
    refs.forEach((r) => r.current && io.observe(r.current));
    return () => io.disconnect();
  }, [refs]);
  return hidden;
};

const Hero = () => (
  <section className="pt-10 text-center sm:pt-14" data-testid="hero-section">
    <span className="reveal lux-chip inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold" style={{ animationDelay: "220ms" }} data-testid="hero-badge">
      <BadgeCheck className="h-3.5 w-3.5" /> {CONTENT.badge}
    </span>
    <h1 className="reveal mt-4 text-[1.7rem] font-bold leading-[1.35] text-white sm:text-4xl" style={{ animationDelay: "260ms" }} data-testid="hero-headline">
      {CONTENT.headline} <span className="text-gold">{CONTENT.headlineAccent}</span>
    </h1>
    <p className="reveal mt-3 text-[15px] leading-relaxed text-slate-400 sm:text-lg" style={{ animationDelay: "300ms" }} data-testid="hero-sub">
      {CONTENT.sub}
    </p>
  </section>
);

export default function Landing() {
  const { loading, join } = useJoin();
  const topRef = useRef(null);
  const ctaRef = useRef(null);
  const bottomRef = useRef(null);
  const refs = useRef([topRef, ctaRef, bottomRef]).current;
  const showSticky = useNoneVisible(refs);

  useEffect(() => {
    trackPageView().catch(() => {});
  }, []);

  return (
    <div className="landing min-h-screen bg-[#07090E] text-slate-200" data-testid="landing-page">
      <div className="glow glow-b" aria-hidden />
      <div className="grain" aria-hidden />
      <main className="relative mx-auto max-w-md px-4 pb-32 sm:max-w-2xl sm:px-6">
        <section className="space-y-3 pt-6 sm:space-y-4 sm:pt-10" data-testid="highlight-cards">
          <CompoundingCard />
          <GiveawayCard />
          <div ref={topRef} className="reveal pt-2" style={{ animationDelay: "220ms" }}>
            <CtaButton testId="top-telegram-cta-button" loading={loading} onClick={join} />
          </div>
        </section>
        <Hero />
        <div className="mt-6">
          <Benefits />
        </div>
        <div ref={ctaRef} className="reveal mt-7" style={{ animationDelay: "560ms" }}>
          <CtaButton testId="landing-telegram-cta-button" loading={loading} onClick={join} />
          <p className="mt-3 text-center text-xs text-slate-500" data-testid="trust-line">{CONTENT.trust}</p>
        </div>
        <Steps />
        <div ref={bottomRef} className="mt-10">
          <CtaButton testId="bottom-telegram-cta-button" loading={loading} onClick={join} />
        </div>
        <div className="lux-rule mx-auto mt-12 w-full opacity-40" />
        <p className="mt-6 text-center text-[11px] leading-relaxed text-slate-600" data-testid="footer-disclaimer">{CONTENT.footer}</p>
      </main>
      <div
        className={`sticky-cta fixed inset-x-0 bottom-0 z-30 border-t border-amber-400/15 bg-[#07090E]/85 px-4 pb-[max(env(safe-area-inset-bottom),12px)] pt-3 backdrop-blur-xl sm:hidden ${
          showSticky ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-full opacity-0"
        }`}
        data-testid="mobile-sticky-cta"
      >
        <CtaButton testId="mobile-sticky-telegram-cta-button" compact loading={loading} onClick={join} />
      </div>
    </div>
  );
}
