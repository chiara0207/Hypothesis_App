import {
  MessageSquare,
  MessagesSquare,
  Search,
  BarChart2,
  ClipboardList,
  BookOpen,
  Table,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  implemented: boolean;
  description: string;
};

export const NAV_ITEMS: NavItem[] = [
  {
    label: "Hypothesis Chat",
    href: "/hypothesis-chat",
    icon: MessageSquare,
    implemented: true,
    description: "Throw any hypothesis at it — scientific, philosophical, or wild — and get an engaged, honest take.",
  },
  {
    label: "Ask Questions on Research Papers",
    href: "/ask-questions",
    icon: MessagesSquare,
    implemented: true,
    description: "Upload a research PDF and ask natural-language questions, answered with cited passages.",
  },
  {
    label: "Find Papers & Datasets",
    href: "/find",
    icon: Search,
    implemented: true,
    description: "Turn a hypothesis into a literature search or an open-dataset search across academic and data registries.",
  },
  {
    label: "Rank Papers",
    href: "/rank-papers",
    icon: BarChart2,
    implemented: true,
    description: "Upload a batch of PDFs and rank them by relevance to your research question.",
  },
  {
    label: "Statistical Analysis",
    href: "/statistical-analysis",
    icon: ClipboardList,
    implemented: true,
    description: "Describe your question in plain language — the AI picks and runs the right statistical test, with charts and interpretation.",
  },
  {
    label: "Statistics Handbook",
    href: "/handbook",
    icon: BookOpen,
    implemented: true,
    description: "Look up core statistics concepts in plain language, or ask the built-in chatbot.",
  },
  {
    label: "Data Preview",
    href: "/data-preview",
    icon: Table,
    implemented: true,
    description: "Inspect your uploaded dataset's rows and column types.",
  },
];
