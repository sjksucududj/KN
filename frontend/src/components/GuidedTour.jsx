import { useState, useEffect, useRef, useCallback } from "react";
import { X, ChevronRight, ChevronLeft, Check, Lightbulb, AlertTriangle } from "lucide-react";

/**
 * GuidedTour - Interactive step-by-step tour with auto-navigation.
 *
 * Step format:
 * {
 *   target: "data-testid-string"  OR  "[data-testid^='order-card-']"   // selector for element to highlight
 *   title: "Judul Langkah",
 *   content: "Step description",
 *   placement: "top" | "bottom" | "left" | "right" | "center",
 *   before: "testid-or-selector",     // optional - element to click BEFORE this step (auto-navigate)
 *   optional: true,                    // optional - if target not found, auto-skip instead of showing error
 *   waitMs: 2500,                      // optional - override default wait time
 * }
 */

const DEFAULT_WAIT_MS = 2500;
const POLL_INTERVAL_MS = 120;

function resolveSelector(targetOrSelector) {
  if (!targetOrSelector) return null;
  // If it already looks like a CSS selector (starts with [, ., #) use as-is
  if (/^[\[.#]/.test(targetOrSelector)) return targetOrSelector;
  return `[data-testid="${targetOrSelector}"]`;
}

function waitForElement(selector, timeoutMs) {
  return new Promise((resolve) => {
    const start = Date.now();
    const tick = () => {
      const el = document.querySelector(selector);
      if (el) return resolve(el);
      if (Date.now() - start >= timeoutMs) return resolve(null);
      setTimeout(tick, POLL_INTERVAL_MS);
    };
    tick();
  });
}

function GuidedTour({ isActive, onClose, steps = [], onComplete, tourId }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [highlightRect, setHighlightRect] = useState(null);
  const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0, placement: "bottom" });
  const [targetMissing, setTargetMissing] = useState(false);
  const [loading, setLoading] = useState(false);
  const resizeRafRef = useRef(null);

  // Reset to step 0 when activated
  useEffect(() => {
    if (isActive) setCurrentStep(0);
  }, [isActive]);

  const updatePositions = useCallback((targetEl, placement) => {
    if (!targetEl) {
      setHighlightRect(null);
      return;
    }
    // NOTE: we use position:fixed for both highlight & tooltip, so we use
    // viewport-relative coords (rect.top/rect.left) WITHOUT scroll offsets.
    const rect = targetEl.getBoundingClientRect();
    setHighlightRect({
      top: rect.top,
      left: rect.left,
      width: rect.width,
      height: rect.height,
    });

    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const margin = 16;
    let tooltipTop = 0;
    let tooltipLeft = 0;
    let finalPlacement = placement || "bottom";

    if (finalPlacement === "center") {
      tooltipTop = vh / 2;
      tooltipLeft = vw / 2;
    } else {
      switch (finalPlacement) {
        case "bottom":
          tooltipTop = rect.bottom + 14;
          tooltipLeft = rect.left + rect.width / 2;
          break;
        case "top":
          tooltipTop = rect.top - 14;
          tooltipLeft = rect.left + rect.width / 2;
          break;
        case "left":
          tooltipTop = rect.top + rect.height / 2;
          tooltipLeft = rect.left - 14;
          break;
        case "right":
          tooltipTop = rect.top + rect.height / 2;
          tooltipLeft = rect.right + 14;
          break;
        default:
          tooltipTop = rect.bottom + 14;
          tooltipLeft = rect.left + rect.width / 2;
      }

      // Clamp tooltip so it stays within viewport. Approx tooltip dims: 380x260
      const halfW = 200;
      const halfH = 130;
      const minLeft = halfW + margin;
      const maxLeft = vw - halfW - margin;
      const minTop = halfH + margin;
      const maxTop = vh - halfH - margin;

      // For non-center placements, ensure tooltip is inside viewport.
      if (finalPlacement === "bottom" || finalPlacement === "top") {
        tooltipLeft = Math.max(minLeft, Math.min(maxLeft, tooltipLeft));
        if (finalPlacement === "bottom" && tooltipTop > maxTop * 1.5) {
          // not enough space below → flip to top
          tooltipTop = Math.max(minTop, rect.top - 14);
          finalPlacement = "top";
        }
        if (finalPlacement === "top" && tooltipTop < minTop) {
          // not enough space above → flip to bottom
          tooltipTop = Math.min(maxTop, rect.bottom + 14);
          finalPlacement = "bottom";
        }
      } else {
        tooltipTop = Math.max(minTop, Math.min(maxTop, tooltipTop));
        if (finalPlacement === "left" && tooltipLeft < minLeft) {
          tooltipLeft = Math.min(maxLeft, rect.right + 14);
          finalPlacement = "right";
        }
        if (finalPlacement === "right" && tooltipLeft > maxLeft) {
          tooltipLeft = Math.max(minLeft, rect.left - 14);
          finalPlacement = "left";
        }
      }
    }

    setTooltipPosition({ top: tooltipTop, left: tooltipLeft, placement: finalPlacement });
  }, []);

  // Main step-handling effect
  useEffect(() => {
    if (!isActive || steps.length === 0) return;
    const step = steps[currentStep];
    if (!step) return;

    let cancelled = false;

    const run = async () => {
      setTargetMissing(false);
      setLoading(true);

      // 1) Execute `before` action (auto-navigate by clicking testid)
      if (step.before) {
        const beforeSelector = resolveSelector(step.before);
        const beforeEl = await waitForElement(beforeSelector, 1500);
        if (beforeEl && typeof beforeEl.click === "function") {
          try { beforeEl.click(); } catch (_) { /* ignore */ }
        }
        // give the UI a tick to re-render
        await new Promise((r) => setTimeout(r, 250));
      }

      // 2) Execute legacy `action` callback if provided
      if (step.action && typeof step.action === "function") {
        try { step.action(); } catch (_) { /* ignore */ }
        await new Promise((r) => setTimeout(r, 200));
      }

      // 3) If placement is center & no target → show as info-only modal
      if (step.placement === "center" && !step.target) {
        if (cancelled) return;
        setHighlightRect(null);
        setTooltipPosition({
          top: window.innerHeight / 2,
          left: window.innerWidth / 2,
          placement: "center",
        });
        setLoading(false);
        return;
      }

      // 4) Resolve target element with polling
      const selector = resolveSelector(step.target);
      const waitMs = step.waitMs ?? DEFAULT_WAIT_MS;
      const el = selector ? await waitForElement(selector, waitMs) : null;
      if (cancelled) return;

      if (!el) {
        // Target not found - reset rect and either auto-skip or mark missing
        setHighlightRect(null);
        if (step.optional && currentStep < steps.length - 1) {
          setLoading(false);
          setCurrentStep((s) => Math.min(s + 1, steps.length - 1));
          return;
        }
        setTargetMissing(true);
        // Center the tooltip on screen as fallback
        setTooltipPosition({
          top: window.innerHeight / 2,
          left: window.innerWidth / 2,
          placement: "center",
        });
        setLoading(false);
        return;
      }

      // 5) Scroll element into view smoothly
      try {
        el.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
      } catch (_) { /* ignore */ }

      // give scroll a beat to settle, then capture position
      await new Promise((r) => setTimeout(r, 280));
      if (cancelled) return;
      updatePositions(el, step.placement || "bottom");
      setLoading(false);
    };

    run();

    return () => { cancelled = true; };
  }, [isActive, currentStep, steps, updatePositions]);

  // Recalculate position on scroll/resize (only when we have an active highlight)
  useEffect(() => {
    if (!isActive) return;
    const step = steps[currentStep];
    if (!step || targetMissing) return;
    const selector = resolveSelector(step.target);
    if (!selector) return;

    const recompute = () => {
      if (resizeRafRef.current) cancelAnimationFrame(resizeRafRef.current);
      resizeRafRef.current = requestAnimationFrame(() => {
        const el = document.querySelector(selector);
        if (el) updatePositions(el, step.placement || "bottom");
      });
    };
    window.addEventListener("scroll", recompute, true);
    window.addEventListener("resize", recompute);
    return () => {
      window.removeEventListener("scroll", recompute, true);
      window.removeEventListener("resize", recompute);
    };
  }, [isActive, currentStep, steps, targetMissing, updatePositions]);

  if (!isActive || steps.length === 0) return null;

  const step = steps[currentStep];
  const isLastStep = currentStep === steps.length - 1;
  const isFirstStep = currentStep === 0;

  const handleNext = () => {
    if (isLastStep) handleComplete();
    else setCurrentStep(currentStep + 1);
  };
  const handlePrev = () => { if (!isFirstStep) setCurrentStep(currentStep - 1); };
  const handleComplete = () => {
    if (tourId) localStorage.setItem(`tour_completed_${tourId}`, "true");
    if (onComplete) onComplete();
    onClose();
  };
  const handleSkip = () => {
    if (tourId) localStorage.setItem(`tour_skipped_${tourId}`, "true");
    onClose();
  };

  const usingCenterFallback = targetMissing || tooltipPosition.placement === "center";

  return (
    <>
      {/* Backdrop: dim screen when no highlight rect (info-only / fallback / loading) */}
      {(!highlightRect || usingCenterFallback) && (
        <div
          className="fixed inset-0 z-[9998] bg-black/55"
          style={{ pointerEvents: "none" }}
          data-testid="tour-backdrop"
        />
      )}

      {/* Highlight cutout — keeps the target visually clear, dims everything else */}
      {highlightRect && !usingCenterFallback && (
        <>
          <div
            className="fixed z-[9998] pointer-events-none"
            data-testid="tour-highlight"
            style={{
              top: highlightRect.top - 6,
              left: highlightRect.left - 6,
              width: highlightRect.width + 12,
              height: highlightRect.height + 12,
              boxShadow:
                "0 0 0 3px rgba(0, 122, 255, 0.95), 0 0 0 9999px rgba(0, 0, 0, 0.55)",
              borderRadius: "10px",
              transition: "all 0.25s ease",
              background: "transparent",
            }}
          />
          <div
            className="fixed z-[10001] pointer-events-none"
            style={{
              top: highlightRect.top - 12,
              left: highlightRect.left - 12,
              width: highlightRect.width + 24,
              height: highlightRect.height + 24,
              border: "2px solid rgba(0, 122, 255, 0.35)",
              borderRadius: "14px",
              transition: "all 0.25s ease",
              animation: "tourPulse 1.6s ease-in-out infinite",
            }}
          />
          <style>{`
            @keyframes tourPulse {
              0%, 100% { opacity: 0.45; transform: scale(1); }
              50% { opacity: 0.95; transform: scale(1.02); }
            }
          `}</style>
        </>
      )}

      {/* Tooltip card */}
      {step && (
        <div
          className="fixed z-[10000] w-[380px] max-w-[92vw] rounded-xl border border-[#007AFF] bg-white shadow-2xl"
          data-testid="tour-tooltip"
          style={{
            top: tooltipPosition.top,
            left: tooltipPosition.left,
            transform:
              tooltipPosition.placement === "bottom" ? "translateX(-50%)" :
              tooltipPosition.placement === "top" ? "translate(-50%, -100%)" :
              tooltipPosition.placement === "left" ? "translate(-100%, -50%)" :
              tooltipPosition.placement === "right" ? "translateY(-50%)" :
              "translate(-50%, -50%)",
            transition: "all 0.25s ease",
          }}
        >
          {/* Header */}
          <div className="flex items-start gap-3 border-b border-[#EFF0F2] p-4 pb-3">
            <div className={`flex-shrink-0 rounded-lg p-2 ${targetMissing ? "bg-orange-100" : "bg-[#EFF4FF]"}`}>
              {targetMissing
                ? <AlertTriangle size={18} className="text-orange-500" />
                : <Lightbulb size={18} className="text-[#007AFF]" />}
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-[14px] font-bold text-[#1C1C1E]" data-testid="tour-step-title">
                {step.title}
              </h3>
              <p className="text-[11px] text-[#6B6B73] mt-0.5">
                Langkah {currentStep + 1} of {steps.length}{loading ? " · memuat…" : ""}
              </p>
            </div>
            <button
              onClick={handleSkip}
              className="flex-shrink-0 text-[#8E8E93] hover:text-black transition-colors"
              data-testid="tour-close-button"
              aria-label="Tutup panduan"
            >
              <X size={18} />
            </button>
          </div>

          {/* Content */}
          <div className="p-4">
            <p className="text-[13px] text-[#3C3C43] leading-relaxed">{step.content}</p>
            {targetMissing && (
              <div className="mt-3 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-[11.5px] text-orange-700">
                Elemen tidak ditemukan di halaman aktif. Tutorial mungkin perlu data dummy
                atau halaman tertentu agar elemen ini muncul. Klik <b>Lanjut</b> untuk melanjutkan
                atau <b>Skip</b> untuk menutup.
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-[#EFF0F2] p-3">
            <button
              onClick={handlePrev}
              disabled={isFirstStep}
              className="secondary-button !py-1.5 !text-[12px]"
              data-testid="tour-prev-button"
            >
              <ChevronLeft size={14} /> Prev
            </button>

            <div className="flex gap-1">
              {steps.map((_, idx) => (
                <div
                  key={idx}
                  className={`h-1.5 rounded-full transition-all ${
                    idx === currentStep
                      ? "w-6 bg-[#007AFF]"
                      : idx < currentStep
                      ? "w-1.5 bg-[#34C759]"
                      : "w-1.5 bg-[#E5E5EA]"
                  }`}
                />
              ))}
            </div>

            <button
              onClick={handleNext}
              className="primary-button !py-1.5 !text-[12px]"
              data-testid="tour-next-button"
            >
              {isLastStep ? (<><Check size={14} /> Complete</>) : (<>Lanjut <ChevronRight size={14} /></>)}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

export default GuidedTour;
