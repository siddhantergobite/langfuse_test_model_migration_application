import { useCallback, useEffect, useState } from "react";

import { KNOWLEDGE_DOCUMENTS_URL } from "../lib/config";

export type KnowledgeDocument = {
  id: string;
  filename: string;
  title: string;
  description: string | null;
  role?: string | null;
  page_count?: number | null;
};

export type VectorIndexStatus = {
  available: boolean;
  collection: string | null;
  indexed_chunks: number | null;
};

type DocumentsResponse = {
  documents: KnowledgeDocument[];
  indexStatus?: VectorIndexStatus | null;
};

export function useKnowledgeDocuments() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [indexStatus, setIndexStatus] = useState<VectorIndexStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(KNOWLEDGE_DOCUMENTS_URL, {
        headers: { Accept: "application/json" },
      });

      if (!response.ok) {
        throw new Error(`Failed to load documents (${response.status})`);
      }

      const payload = (await response.json()) as DocumentsResponse;
      setDocuments(payload.documents ?? []);
      setIndexStatus(payload.indexStatus ?? null);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setDocuments([]);
      setIndexStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  return { documents, indexStatus, loading, error, refresh: fetchDocuments };
}
