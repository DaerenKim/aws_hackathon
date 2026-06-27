"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

export interface ApprovalDialogProps {
  gateNumber: number;
  onApprove: () => void;
  onRequestChange: (feedback: string) => void;
}

/**
 * Approval gate dialog with approve and request-change actions.
 * Request-change reveals a text area for feedback input.
 */
export function ApprovalDialog({
  gateNumber,
  onApprove,
  onRequestChange,
}: ApprovalDialogProps) {
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedback, setFeedback] = useState("");

  const handleRequestChange = () => {
    if (!showFeedback) {
      setShowFeedback(true);
      return;
    }

    if (feedback.trim()) {
      onRequestChange(feedback.trim());
      setFeedback("");
      setShowFeedback(false);
    }
  };

  const handleApprove = () => {
    onApprove();
  };

  return (
    <div className="rounded-lg border bg-card shadow-sm p-4 md:p-6 w-full max-w-lg">
      {/* Header */}
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-card-foreground">
          Approval Gate {gateNumber}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Review the artifacts and approve to continue, or request changes.
        </p>
      </div>

      {/* Feedback area (shown when requesting changes) */}
      {showFeedback && (
        <div className="mb-4">
          <label
            htmlFor="feedback-input"
            className="block text-sm font-medium text-foreground mb-1.5"
          >
            Describe the changes needed
          </label>
          <textarea
            id="feedback-input"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="What would you like changed?"
            rows={4}
            className={cn(
              "w-full rounded-md border bg-background px-3 py-2 text-sm",
              "placeholder:text-muted-foreground",
              "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
              "resize-y min-h-[80px]"
            )}
          />
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
        <button
          type="button"
          onClick={handleRequestChange}
          className={cn(
            "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors",
            "border border-border bg-background text-foreground",
            "hover:bg-muted focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
            showFeedback && !feedback.trim() && "opacity-50 cursor-not-allowed"
          )}
          disabled={showFeedback && !feedback.trim()}
        >
          {showFeedback ? "Submit Feedback" : "Request Changes"}
        </button>

        <button
          type="button"
          onClick={handleApprove}
          className={cn(
            "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors",
            "bg-primary text-primary-foreground",
            "hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
          )}
        >
          Approve
        </button>
      </div>
    </div>
  );
}
