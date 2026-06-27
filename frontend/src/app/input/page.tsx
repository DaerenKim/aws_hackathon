"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { FileUpload } from "@/components/file-upload";
import { apiClient, ApiError } from "@/lib/api";
import type { ValidationError } from "@/lib/types";

/**
 * Input Collection Page
 *
 * Allows users to upload hackathon brief and judging rubric documents,
 * enter their project idea and optional tech stack, then submit all
 * inputs to the backend for validation and processing.
 *
 * Requirements: 1.1-1.6
 */
export default function InputPage() {
  const router = useRouter();

  // File state
  const [briefFile, setBriefFile] = useState<File | null>(null);
  const [rubricFile, setRubricFile] = useState<File | null>(null);

  // Text input state
  const [projectIdea, setProjectIdea] = useState("");
  const [techStack, setTechStack] = useState("");

  // UI state
  const [errors, setErrors] = useState<ValidationError[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Client-side validation
  function validate(): ValidationError[] {
    const validationErrors: ValidationError[] = [];

    if (!briefFile) {
      validationErrors.push({
        field: "hackathon_brief",
        reason: "empty_content",
        detail: "Hackathon brief is required.",
      });
    }

    if (!rubricFile) {
      validationErrors.push({
        field: "judging_rubric",
        reason: "empty_content",
        detail: "Judging rubric is required.",
      });
    }

    if (!projectIdea.trim()) {
      validationErrors.push({
        field: "project_idea",
        reason: "length_constraint",
        detail: "Project idea is required (1-5000 characters).",
      });
    } else if (projectIdea.length > 5000) {
      validationErrors.push({
        field: "project_idea",
        reason: "length_constraint",
        detail: `Project idea exceeds 5000 characters (currently ${projectIdea.length}).`,
      });
    }

    if (techStack.length > 2000) {
      validationErrors.push({
        field: "tech_stack",
        reason: "length_constraint",
        detail: `Tech stack exceeds 2000 characters (currently ${techStack.length}).`,
      });
    }

    return validationErrors;
  }

  // Get error messages for a specific field
  function getFieldErrors(field: string): ValidationError[] {
    return errors.filter((e) => e.field === field);
  }

  // Handle file upload from FileUpload component
  function handleBriefUpload(file: File) {
    setBriefFile(file);
    // Clear any existing errors for this field
    setErrors((prev) => prev.filter((e) => e.field !== "hackathon_brief"));
  }

  function handleRubricUpload(file: File) {
    setRubricFile(file);
    setErrors((prev) => prev.filter((e) => e.field !== "judging_rubric"));
  }

  // Submit all inputs
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    setErrors([]);

    // Client-side validation
    const validationErrors = validate();
    if (validationErrors.length > 0) {
      setErrors(validationErrors);
      return;
    }

    setIsSubmitting(true);

    try {
      // Upload hackathon brief
      const briefResult = await apiClient.uploadFile(
        briefFile!,
        "hackathon_brief"
      );
      if (!briefResult.valid) {
        setErrors((prev) => [...prev, ...briefResult.errors]);
        setIsSubmitting(false);
        return;
      }

      // Upload judging rubric
      const rubricResult = await apiClient.uploadFile(
        rubricFile!,
        "judging_rubric"
      );
      if (!rubricResult.valid) {
        setErrors((prev) => [...prev, ...rubricResult.errors]);
        setIsSubmitting(false);
        return;
      }

      // Submit text inputs
      const submitResult = await apiClient.submitInputs(
        projectIdea,
        techStack.trim() || undefined
      );
      if (!submitResult.valid) {
        setErrors((prev) => [...prev, ...submitResult.errors]);
        setIsSubmitting(false);
        return;
      }

      // All inputs valid — redirect to monitoring page
      router.push("/monitor");
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(err.detail);
      } else {
        setSubmitError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            Input Collection
          </h1>
          <p className="mt-2 text-muted-foreground">
            Upload your hackathon materials and describe your project idea. The
            AI agents will use these inputs to generate your MVP.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* File Uploads Section */}
          <section className="space-y-6">
            <h2 className="text-xl font-semibold text-foreground">Documents</h2>

            {/* Hackathon Brief Upload */}
            <div>
              <FileUpload
                onUpload={handleBriefUpload}
                fieldName="hackathon_brief"
                label="Hackathon Brief *"
                accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
              />
              {getFieldErrors("hackathon_brief").map((err, i) => (
                <p
                  key={i}
                  className="mt-1.5 text-xs text-red-600"
                  role="alert"
                >
                  {err.detail}
                </p>
              ))}
            </div>

            {/* Judging Rubric Upload */}
            <div>
              <FileUpload
                onUpload={handleRubricUpload}
                fieldName="judging_rubric"
                label="Judging Rubric *"
                accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
              />
              {getFieldErrors("judging_rubric").map((err, i) => (
                <p
                  key={i}
                  className="mt-1.5 text-xs text-red-600"
                  role="alert"
                >
                  {err.detail}
                </p>
              ))}
            </div>
          </section>

          {/* Text Inputs Section */}
          <section className="space-y-6">
            <h2 className="text-xl font-semibold text-foreground">
              Project Details
            </h2>

            {/* Project Idea */}
            <div>
              <label
                htmlFor="project-idea"
                className="block text-sm font-medium text-foreground mb-1.5"
              >
                Project Idea *
              </label>
              <textarea
                id="project-idea"
                value={projectIdea}
                onChange={(e) => {
                  setProjectIdea(e.target.value);
                  setErrors((prev) =>
                    prev.filter((err) => err.field !== "project_idea")
                  );
                }}
                placeholder="Describe your project idea in detail (1-5000 characters)..."
                rows={6}
                maxLength={5000}
                className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary resize-y"
              />
              <div className="mt-1 flex items-center justify-between">
                <div>
                  {getFieldErrors("project_idea").map((err, i) => (
                    <p key={i} className="text-xs text-red-600" role="alert">
                      {err.detail}
                    </p>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  {projectIdea.length}/5000
                </p>
              </div>
            </div>

            {/* Tech Stack (Optional) */}
            <div>
              <label
                htmlFor="tech-stack"
                className="block text-sm font-medium text-foreground mb-1.5"
              >
                Preferred Tech Stack{" "}
                <span className="text-muted-foreground font-normal">
                  (optional)
                </span>
              </label>
              <textarea
                id="tech-stack"
                value={techStack}
                onChange={(e) => {
                  setTechStack(e.target.value);
                  setErrors((prev) =>
                    prev.filter((err) => err.field !== "tech_stack")
                  );
                }}
                placeholder="e.g., React, FastAPI, PostgreSQL, TailwindCSS..."
                rows={3}
                maxLength={2000}
                className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary resize-y"
              />
              <div className="mt-1 flex items-center justify-between">
                <div>
                  {getFieldErrors("tech_stack").map((err, i) => (
                    <p key={i} className="text-xs text-red-600" role="alert">
                      {err.detail}
                    </p>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  {techStack.length}/2000
                </p>
              </div>
            </div>
          </section>

          {/* General submit error */}
          {submitError && (
            <div
              className="rounded-lg border border-red-200 bg-red-50 px-4 py-3"
              role="alert"
            >
              <p className="text-sm text-red-700">{submitError}</p>
            </div>
          )}

          {/* Submit Button */}
          <div className="pt-4">
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full sm:w-auto rounded-lg bg-primary px-8 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? "Submitting..." : "Submit Inputs"}
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
