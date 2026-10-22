import { Coins, Gift, ArrowDown } from "lucide-react";
import { CONTENT } from "@/content";

const BARS = [22, 34, 46, 60, 76, 100];

export const CompoundingCard = () => {
  const c = CONTENT.compounding;
  return (
    <div className="reveal lux-card lux-gold relative overflow-hidden rounded-[28px] p-6 sm:p-8" style={{ animationDelay: "80ms" }} data-testid="compounding-card">
      <div className="lux-sheen" aria-hidden />
      <div className="relative flex items-center justify-between gap-3">
        <span className="lux-chip inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold tracking-wide">
          <Coins className="h-3.5 w-3.5" /> {c.tag}
        </span>
      </div>
      <div className="relative mt-5 flex items-end justify-between gap-4">
        <div className="flex items-baseline gap-2.5 sm:gap-3" data-testid="compounding-range">
          <span className="lux-num text-3xl font-bold text-slate-300 sm:text-4xl">{c.from}</span>
          <span className="text-xl text-amber-300/70 sm:text-2xl">→</span>
          <span className="lux-num text-gold text-5xl font-extrabold sm:text-6xl">{c.to}</span>
        </div>
        <div className="flex h-14 items-end gap-1 sm:h-16" aria-hidden>
          {BARS.map((h, i) => (
            <span key={h} className="lux-bar w-1.5 rounded-full sm:w-2" style={{ height: `${h}%`, animationDelay: `${400 + i * 90}ms` }} />
          ))}
        </div>
      </div>
      <div className="lux-rule relative my-5" />
      <h2 className="relative text-lg font-bold leading-snug text-white sm:text-2xl" data-testid="compounding-title">{c.title}</h2>
      <p className="relative mt-2 flex items-start gap-2 text-sm leading-relaxed text-amber-100/75 sm:text-base" data-testid="compounding-desc">
        <ArrowDown className="mt-0.5 h-4 w-4 shrink-0 animate-bounce text-amber-300" />
        {c.desc}
      </p>
    </div>
  );
};

export const GiveawayCard = () => {
  const g = CONTENT.giveaway;
  return (
    <div className="reveal lux-card lux-emerald flex items-center gap-4 rounded-[24px] p-5 sm:p-6" style={{ animationDelay: "170ms" }} data-testid="giveaway-card">
      <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-emerald-300/25 bg-gradient-to-br from-emerald-400/25 to-emerald-700/10 text-emerald-200">
        <Gift className="h-7 w-7" />
      </span>
      <span className="min-w-0">
        <span className="block text-base font-bold text-white sm:text-lg" data-testid="giveaway-title">{g.title}</span>
        <span className="mt-1 block text-sm leading-relaxed text-slate-300/80" data-testid="giveaway-desc">{g.desc}</span>
      </span>
    </div>
  );
};
