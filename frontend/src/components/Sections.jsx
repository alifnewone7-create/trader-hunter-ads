import { Zap, ShieldCheck, BellRing } from "lucide-react";
import { CONTENT } from "@/content";

const ICONS = { Zap, ShieldCheck, BellRing };

export const Benefits = () => (
  <ul className="grid gap-3 sm:grid-cols-3" data-testid="benefits-list">
    {CONTENT.benefits.map((b, i) => {
      const Icon = ICONS[b.icon];
      return (
        <li
          key={b.title}
          data-testid={`benefit-item-${i}`}
          className="reveal lux-card lux-plain flex items-start gap-3.5 rounded-2xl p-4 sm:flex-col sm:gap-3"
          style={{ animationDelay: `${300 + i * 90}ms` }}
        >
          <span className="lux-icon flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
            <Icon className="h-5 w-5" />
          </span>
          <span>
            <span className="block font-semibold leading-snug text-white">{b.title}</span>
            <span className="mt-0.5 block text-sm leading-relaxed text-slate-400">{b.desc}</span>
          </span>
        </li>
      );
    })}
  </ul>
);

export const Steps = () => (
  <section className="mt-16 sm:mt-20" data-testid="steps-section">
    <p className="text-center text-[11px] font-semibold uppercase tracking-[0.3em] text-amber-300/70">How to join</p>
    <h2 className="mt-2 text-center text-2xl font-bold text-white sm:text-3xl">{CONTENT.stepsTitle}</h2>
    <div className="lux-rule mx-auto mt-4 w-24" />
    <ol className="mt-8 grid gap-3 sm:grid-cols-3">
      {CONTENT.steps.map((s, i) => (
        <li key={s.title} className="lux-card lux-plain relative flex gap-4 rounded-2xl p-4 sm:flex-col" data-testid={`step-item-${i}`}>
          <span className="lux-step flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-lg font-bold">
            {["১", "২", "৩"][i]}
          </span>
          <span className="pt-1">
            <span className="block font-semibold text-white">{s.title}</span>
            <span className="mt-0.5 block text-sm leading-relaxed text-slate-400">{s.desc}</span>
          </span>
        </li>
      ))}
    </ol>
  </section>
);
