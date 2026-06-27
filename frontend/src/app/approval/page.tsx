'use client';

import { useCallback, useMemo, useState } from 'react';

import { ApprovalDialog } from '@/components/approval-dialog';
import { useProjectState } from '@/hooks/use-project-state';
import { apiClient } from '@/lib/api';
import type { ApprovalGateState, PhaseStatus } from '@/lib/types';

/** Gate metadata describing artifacts, descriptions, and next actions per gate. */
const GATE_CONFIG: Record<
  number,
  {
    title: string;
    artifacts: { name: string; description: string }[];
    nextActions: string;
  }
> = {
  1: {
    title: 'Architecture Review',
    artifacts: [
      {
        name: 'architecture.md',
        description:
          'System architecture including folder structure, API endpoints, database schema, component hierarchy, and integration points.',
      },
      {
        name: 'roadmap.md',
        description:
          'Ordered task breakdown with dependency graph and completion phases assigned to each agent.',
      },
    ],
    nextActions:
      'Upon approval, the system will begin parallel development — Backend and Frontend engineers will start building the application.',
  },
  2: {
    title: 'QA Testing Review',
    artifacts: [
      {
        name: 'testing_report.md',
        description:
          'Full testing report with unit, integration, and UI test results, pass/fail counts, bug descriptions, and severity ratings.',
      },
    ],
    nextActions:
      'Upon approval, the system will proceed to the Delivery phase — Documentation, Presentation, Demo Video, and GitHub push will execute in parallel.',
  },
  3: {
    title: 'Final Delivery Review',
    artifacts: [
      {
        name: 'Repository URL',
        description: 'The public GitHub repository with all project code committed and organized.',
      },
      {
        name: 'Documentation',
        description: 'README.md, developer_guide.md, and api_docs.md with comprehensive project documentation.',
      },
      {
        name: 'Presentation',
        description: 'Hackathon presentation slides (6-15 slides) with speaker notes.',
      },
      {
        name: 'Demo Video',
        description: 'Recorded demo walkthrough (60-300s) with voiceover and captions.',
      },
    ],
    nextActions:
      'Upon approval, the project will be marked as complete. All deliverables will be available for download.',
  },
};

/** Maps phase status to completed phase labels. */
function getCompletedPhases(phase: PhaseStatus, gateNumber: number): string[] {
  if (phase === 'delivery' && gateNumber >= 3) {
    return [
      'Planning (Project Spec, Judge Analysis, Architecture)',
      'Development (Backend, Frontend, Integration, QA)',
      'Delivery (Documentation, Presentation, Video, GitHub)',
    ];
  }
  if (phase === 'development' || (phase === 'delivery' && gateNumber >= 2)) {
    return [
      'Planning (Project Spec, Judge Analysis, Architecture)',
      'Development (Backend, Frontend, Integration, QA)',
    ];
  }
  if (gateNumber >= 1) {
    return ['Planning (Project Spec, Judge Analysis, Architecture)'];
  }
  return [];
}

export default function ApprovalPage() {
  const { state, isLoading, error } = useProjectState();
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Detect which gate is currently pending
  const pendingGate: ApprovalGateState | null = useMemo(() => {
    if (!state?.approval_gates) return null;

    for (const gate of Object.values(state.approval_gates)) {
      if (gate.pending) {
        return gate;
      }
    }
    return null;
  }, [state]);

  const gateNumber = pendingGate?.gate_number ?? 0;
  const gateConfig = gateNumber > 0 ? GATE_CONFIG[gateNumber] : null;

  const completedPhases = useMemo(() => {
    if (!state || !gateNumber) return [];
    return getCompletedPhases(state.phase, gateNumber);
  }, [state, gateNumber]);

  const handleApprove = useCallback(async () => {
    if (!gateNumber) return;
    setIsSubmitting(true);
    setActionError(null);
    setSuccessMessage(null);

    try {
      const response = await apiClient.approve(gateNumber);
      setSuccessMessage(response.message || `Gate ${gateNumber} approved successfully. Workflow resuming...`);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : 'Failed to approve. Please try again.'
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [gateNumber]);

  const handleRequestChange = useCallback(
    async (feedback: string) => {
      if (!gateNumber) return;
      setIsSubmitting(true);
      setActionError(null);
      setSuccessMessage(null);

      try {
        const response = await apiClient.requestChange(gateNumber, feedback);
        setSuccessMessage(
          response.message || `Change request submitted for Gate ${gateNumber}. Revision in progress...`
        );
      } catch (err) {
        setActionError(
          err instanceof Error ? err.message : 'Failed to submit change request. Please try again.'
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [gateNumber]
  );

  // --- Loading state ---
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4" />
          <p className="text-muted-foreground text-sm">Loading project state...</p>
        </div>
      </div>
    );
  }

  // --- Connection error ---
  if (error && !state) {
    return (
      <div className="flex items-center justify-center min-h-[60vh] px-4">
        <div className="text-center max-w-md">
          <div className="text-red-500 text-3xl mb-3">⚠</div>
          <h2 className="text-lg font-semibold text-foreground mb-2">Connection Error</h2>
          <p className="text-sm text-muted-foreground">{error.message}</p>
        </div>
      </div>
    );
  }

  // --- No pending gate ---
  if (!pendingGate || !gateConfig) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 md:py-12">
        <div className="text-center">
          <div className="text-4xl mb-4">✓</div>
          <h1 className="text-2xl font-bold text-foreground mb-2">No Pending Approval</h1>
          <p className="text-muted-foreground">
            There are no approval gates waiting for review right now. The workflow is either in
            progress or has completed.
          </p>
          {state && (
            <p className="mt-4 text-sm text-muted-foreground">
              Current phase: <span className="font-medium text-foreground capitalize">{state.phase}</span>
            </p>
          )}
        </div>
      </div>
    );
  }

  // --- Pending gate UI ---
  return (
    <div className="max-w-4xl mx-auto px-4 py-8 md:py-12">
      {/* Page header */}
      <header className="mb-8">
        <h1 className="text-2xl md:text-3xl font-bold text-foreground">
          {gateConfig.title}
        </h1>
        <p className="mt-2 text-muted-foreground">
          Approval Gate {gateNumber} — Review the artifacts below and approve to continue.
        </p>
        {pendingGate.revision_count > 0 && (
          <p className="mt-1 text-sm text-amber-600">
            Revision cycle {pendingGate.revision_count} of 5
          </p>
        )}
      </header>

      {/* Completed phases summary */}
      {completedPhases.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-foreground mb-3">Completed Phases</h2>
          <ul className="space-y-2">
            {completedPhases.map((phase) => (
              <li key={phase} className="flex items-start gap-2 text-sm">
                <span className="text-green-500 mt-0.5">✓</span>
                <span className="text-foreground">{phase}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Artifacts for review */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-foreground mb-3">Artifacts for Review</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {gateConfig.artifacts.map((artifact) => (
            <div
              key={artifact.name}
              className="rounded-lg border bg-card p-4 shadow-sm"
            >
              <h3 className="font-medium text-card-foreground mb-1">{artifact.name}</h3>
              <p className="text-sm text-muted-foreground">{artifact.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Next actions */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-foreground mb-3">Next Actions</h2>
        <p className="text-sm text-muted-foreground bg-muted/50 rounded-lg p-4 border">
          {gateConfig.nextActions}
        </p>
      </section>

      {/* Success / error messages */}
      {successMessage && (
        <div className="mb-6 rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800">
          {successMessage}
        </div>
      )}
      {actionError && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {actionError}
        </div>
      )}

      {/* Approval dialog */}
      <section className="flex justify-center">
        <div className={isSubmitting ? 'opacity-50 pointer-events-none' : ''}>
          <ApprovalDialog
            gateNumber={gateNumber}
            onApprove={handleApprove}
            onRequestChange={handleRequestChange}
          />
        </div>
      </section>
    </div>
  );
}
