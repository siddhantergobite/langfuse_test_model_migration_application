import { StartScreenPrompt } from "@openai/chatkit";

export const THEME_STORAGE_KEY = "knowledge-assistant-theme";

const KNOWLEDGE_API_BASE =
  import.meta.env.VITE_KNOWLEDGE_API_BASE ?? "/knowledge";

export const KNOWLEDGE_CHATKIT_API_URL =
  import.meta.env.VITE_KNOWLEDGE_CHATKIT_API_URL ??
  `${KNOWLEDGE_API_BASE}/chatkit`;

/**
 * ChatKit still expects a domain key at runtime. Use any placeholder locally,
 * but register your production domain at
 * https://platform.openai.com/settings/organization/security/domain-allowlist
 * and deploy the real key.
 */
export const KNOWLEDGE_CHATKIT_API_DOMAIN_KEY =
  import.meta.env.VITE_KNOWLEDGE_CHATKIT_API_DOMAIN_KEY ?? "domain_pk_localhost_dev";

export const KNOWLEDGE_DOCUMENTS_URL =
  import.meta.env.VITE_KNOWLEDGE_DOCUMENTS_URL ??
  `${KNOWLEDGE_API_BASE}/documents`;

export const KNOWLEDGE_DOCUMENT_FILE_URL = (documentId: string): string =>
  `${
    import.meta.env.VITE_KNOWLEDGE_DOCUMENT_FILE_BASE_URL ??
    `${KNOWLEDGE_API_BASE}/documents`
  }/${documentId}/file`;

export const getKnowledgeThreadCitationsUrl = (threadId: string): string =>
  `${
    import.meta.env.VITE_KNOWLEDGE_THREADS_BASE_URL ??
    `${KNOWLEDGE_API_BASE}/threads`
  }/${threadId}/citations`;

export const KNOWLEDGE_GREETING =
  import.meta.env.VITE_KNOWLEDGE_GREETING ??
  "Search the candidate resume library";

export const KNOWLEDGE_STARTER_PROMPTS: StartScreenPrompt[] = [
  {
    label: "AI experience",
    prompt: "Which candidates have professional AI or machine learning experience?",
    icon: "sparkle",
  },
  {
    label: "Compare candidates",
    prompt: "Compare the AI candidates' experience, skills, and selected projects.",
    icon: "notebook",
  },
  {
    label: "Find a skill",
    prompt: "Who has experience with Python, FastAPI, and cloud deployment?",
    icon: "chart",
  },
  {
    label: "Candidate summary",
    prompt: "Summarize Meera Nair's professional experience and key achievements.",
    icon: "notebook",
  },
];

export const KNOWLEDGE_COMPOSER_PLACEHOLDER =
  import.meta.env.VITE_KNOWLEDGE_COMPOSER_PLACEHOLDER ??
  "Ask about candidate skills, experience, or projects";
