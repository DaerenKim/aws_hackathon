import Link from "next/link";

const sections = [
  {
    title: "Input Collection",
    description:
      "Upload your hackathon brief, judging rubric, project idea, and preferred tech stack to get started.",
    href: "/input",
    icon: "📥",
  },
  {
    title: "Agent Monitor",
    description:
      "Watch all 10 AI agents work in real time. Track progress through Planning, Development, and Delivery phases.",
    href: "/monitor",
    icon: "📡",
  },
  {
    title: "Approval Gates",
    description:
      "Review and approve the system's plans at critical milestones before it proceeds to the next phase.",
    href: "/approval",
    icon: "✅",
  },
  {
    title: "Deliverables",
    description:
      "Download your complete MVP: source code, documentation, presentation slides, demo video, and more.",
    href: "/deliverables",
    icon: "📦",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-50 p-6 md:p-10">
      <div className="mx-auto max-w-5xl">
        {/* Hero Section */}
        <div className="mb-12 text-center">
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
            Hackathon Studio
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-gray-600">
            An autonomous multi-agent AI software studio that transforms your
            hackathon brief, judging rubric, and project idea into a complete
            hackathon-ready MVP.
          </p>
          <p className="mx-auto mt-2 max-w-2xl text-sm text-gray-500">
            10 specialized AI agents collaborate through Planning, Development,
            and Delivery phases with human approval gates at critical milestones.
          </p>
        </div>

        {/* Navigation Cards */}
        <div className="grid gap-6 sm:grid-cols-2">
          {sections.map((section) => (
            <Link
              key={section.href}
              href={section.href}
              className="group rounded-xl border border-gray-200 bg-white p-6 shadow-sm transition-all hover:border-blue-300 hover:shadow-md"
            >
              <div className="flex items-start gap-4">
                <span className="text-3xl" aria-hidden="true">
                  {section.icon}
                </span>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 group-hover:text-blue-700">
                    {section.title}
                  </h2>
                  <p className="mt-1 text-sm text-gray-600">
                    {section.description}
                  </p>
                </div>
              </div>
            </Link>
          ))}
        </div>

        {/* Footer Note */}
        <p className="mt-12 text-center text-xs text-gray-400">
          Powered by Ollama (local LLM) • LangGraph orchestration • Next.js
          dashboard
        </p>
      </div>
    </main>
  );
}
