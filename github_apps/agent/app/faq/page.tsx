"use client";
import ListArticles from "@/components/ListArticles";

// Page showing all FAQ articles in /faq folder
export default function KnowledgeBasePage() {
  return (
    <div>
      <ListArticles page="faq" folder="faq" title="Public FAQ" />
    </div>
  );
}
