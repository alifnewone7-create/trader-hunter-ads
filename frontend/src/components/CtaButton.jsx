import { useState } from "react";
import { Loader2 } from "lucide-react";
import { TelegramIcon } from "@/components/TelegramIcon";
import { getDeepLink } from "@/lib/tracking";
import { CONTENT } from "@/content";

export const useJoin = () => {
  const [loading, setLoading] = useState(false);
  const join = async () => {
    if (loading) return;
    setLoading(true);
    const link = await getDeepLink();
    if (link) window.location.href = link;
    setTimeout(() => setLoading(false), 2500);
  };
  return { loading, join };
};

export const CtaButton = ({ testId, compact = false, loading, onClick }) => (
  <button
    data-testid={testId}
    onClick={onClick}
    disabled={loading}
    className={`cta-btn cta-shake group relative w-full overflow-hidden rounded-2xl text-white font-bold tracking-wide ${
      compact ? "py-3.5 text-base" : "py-4 sm:py-5 text-lg sm:text-xl"
    }`}
  >
    <span className="cta-shine" aria-hidden />
    <span className="relative flex items-center justify-center gap-3">
      {loading ? (
        <Loader2 className="h-6 w-6 animate-spin" />
      ) : (
        <TelegramIcon className="h-7 w-7 shrink-0 transition-transform duration-300 group-hover:scale-110" />
      )}
      <span>{loading ? CONTENT.ctaLoading : compact ? CONTENT.stickyCta : CONTENT.cta}</span>
    </span>
  </button>
);
