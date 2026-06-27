"use client";

import type { PhaseStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface PhaseIndicatorProps {
  currentPhase: PhaseStatus;
}

const phases: { key: PhaseStatus; label: string }[] = [
  { key: "planning", label: "Planning" },
  { key: "development", label: "Development" },
  { key: "delivery", label: "Delivery" },
  { key: "complete", label: "Complete" },
];

/**
 * Displays the current workflow phase as a labeled header with a step progress bar.
 * Shows which phase is active: Planning → Development → Delivery → Complete.
 */
export function PhaseIndicator({ currentPhase }: PhaseIndicatorProps) {
  const currentIndex = phases.findIndex((p) => p.key === currentPhase);

  return (
    <div className="w-full">
      <h2 className="text-lg font-semibold text-foreground mb-3">
        Phase: {phases[currentIndex]?.label ?? currentPhase}
      </h2>

      {/* Progress steps */}
      <div className="flex items-center gap-1 md:gap-2">
        {phases.map((phase, index) => {
          const isCompleted = index < currentIndex;
          const isActive = index === currentIndex;

          return (
            <div key={phase.key} className="flex items-center flex-1">
              {/* Step indicator */}
              <div className="flex flex-col items-center flex-1">
                <div
                  className={cn(
                    "flex items-center justify-center w-8 h-8 rounded-full border-2 text-xs font-bold transition-colors",
                    isCompleted &&
                      "bg-green-500 border-green-500 text-white",
                    isActive &&
                      "bg-blue-500 border-blue-500 text-white",
                    !isCompleted &&
                      !isActive &&
                      "bg-muted border-border text-muted-foreground"
                  )}
                >
                  {isCompleted ? "✓" : index + 1}
                </div>
                <span
                  className={cn(
                    "mt-1 text-[10px] md:text-xs text-center leading-tight",
                    isActive && "font-semibold text-foreground",
                    isCompleted && "text-green-600",
                    !isActive && !isCompleted && "text-muted-foreground"
                  )}
                >
                  {phase.label}
                </span>
              </div>

              {/* Connecting line (except after last) */}
              {index < phases.length - 1 && (
                <div
                  className={cn(
                    "h-0.5 flex-1 mx-1",
                    index < currentIndex ? "bg-green-500" : "bg-border"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
