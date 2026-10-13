import { ChatKit, useChatKit } from "@openai/chatkit-react";
import type { ColorScheme } from "../hooks/useColorScheme";
import type { VectorIndexStatus } from "../hooks/useKnowledgeDocuments";
import {
  KNOWLEDGE_CHATKIT_API_DOMAIN_KEY,
  KNOWLEDGE_CHATKIT_API_URL,
  KNOWLEDGE_COMPOSER_PLACEHOLDER,
  KNOWLEDGE_GREETING,
  KNOWLEDGE_STARTER_PROMPTS,
} from "../lib/config";

type ChatKitPanelProps = {
  theme: ColorScheme;
  indexStatus: VectorIndexStatus | null;
  checkingIndex: boolean;
  onRetryIndex: () => void;
  onThreadChange: (threadId: string | null) => void;
  onResponseCompleted: () => void;
};

export function ChatKitPanel({
  theme,
  indexStatus,
  checkingIndex,
  onRetryIndex,
  onThreadChange,
  onResponseCompleted,
}: ChatKitPanelProps) {
  const canRetrieve = Boolean(
    indexStatus?.available &&
      typeof indexStatus.indexed_chunks === "number" &&
      indexStatus.indexed_chunks > 0,
  );

  const chatkit = useChatKit({
    api: {
      url: KNOWLEDGE_CHATKIT_API_URL,
      domainKey: KNOWLEDGE_CHATKIT_API_DOMAIN_KEY,
    },
    theme: {
      colorScheme: theme,
      color: {
        grayscale: {
          hue: 225,
          tint: 6,
          shade: theme === "dark" ? -1 : -4,
        },
        accent: {
          primary: theme === "dark" ? "#f1f5f9" : "#0f172a",
          level: 1,
        },
      },
      radius: "round",
    },
    startScreen: {
      greeting: KNOWLEDGE_GREETING,
      prompts: KNOWLEDGE_STARTER_PROMPTS,
    },
    composer: {
      placeholder: KNOWLEDGE_COMPOSER_PLACEHOLDER,
    },
    threadItemActions: {
      feedback: false,
    },
    onResponseEnd: () => {
      onResponseCompleted();
    },
    onThreadChange: ({ threadId }) => {
      onThreadChange(threadId ?? null);
    },
    onError: ({ error }) => {
      // ChatKit propagates the error to the UI; keep logging for debugging.
      console.error("ChatKit error", error);
    },
  });

  if (!canRetrieve) {
    const title = checkingIndex
      ? "Checking resume index"
      : !indexStatus
        ? "Resume index status unavailable"
        : !indexStatus.available
          ? "Resume search is unavailable"
          : "Resume chunks are not indexed yet";
    const description = checkingIndex
      ? "Checking whether the resume collection is ready for retrieval."
      : !indexStatus
        ? "The app could not read the index status. Retry the check after confirming the backend is running."
        : !indexStatus.available
          ? "The resume vector collection is unavailable. Start Qdrant, then refresh the index status."
          : "The 8 resume PDFs are visible in the library, but the collection contains 0 searchable chunks. Configure the gateway key and run resume ingestion before asking questions.";

    return (
      <div className="flex h-full w-full items-center justify-center border border-slate-200/60 bg-white p-8 dark:border-slate-800/70 dark:bg-slate-900">
        <div className="max-w-sm text-center" role="status" aria-live="polite">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
            Resume retrieval
          </p>
          <h2 className="mt-3 text-xl font-semibold text-slate-800 dark:text-slate-100">
            {title}
          </h2>
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
            {description}
          </p>
          {!checkingIndex ? (
            <button
              type="button"
              onClick={onRetryIndex}
              className="mt-5 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
            >
              Refresh index status
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full overflow-hidden border border-slate-200/60 bg-white shadow-card dark:border-slate-800/70 dark:bg-slate-900">
      <ChatKit control={chatkit.control} className="block h-full w-full" />
    </div>
  );
}
