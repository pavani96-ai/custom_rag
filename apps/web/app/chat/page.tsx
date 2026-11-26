"use client";

/**
 * Chat screen for one collection. Lists saved conversations, streams each answer, shows
 * numbered citations, and opens the cited page of the stored original in a new tab.
 */

import { type FormEvent, useEffect, useState } from "react";

import {
  apiBase,
  type ChatMessage,
  type CitedPassage,
  type ConversationSummary,
  getConversation,
  listConversations,
  originalUrl,
} from "../../lib/api";
import { answerLines, splitCitations } from "../../lib/citations";
import { streamChat, withMessage } from "../../lib/chat-stream";

const PENDING_USER = "pending-user";
const PENDING_ASSISTANT = "pending-assistant";

/** Read the collection ID from the page URL, or an empty string when it is missing. */
function collectionFromUrl(): string {
  return new URLSearchParams(window.location.search).get("collection") ?? "";
}

/** Render one line of an answer, with each [n] marker as a button that selects that citation. */
function renderSegments(
  text: string,
  citations: CitedPassage[],
  onSelect: (citation: CitedPassage) => void,
) {
  const byId = new Map(citations.map((citation) => [citation.source_id, citation]));
  return splitCitations(text).map((segment, index) => {
    if (segment.kind === "text") {
      return <span key={index}>{segment.text}</span>;
    }
    const citation = byId.get(segment.id);
    if (!citation) {
      return <span key={index}>[{segment.id}]</span>;
    }
    return (
      <button
        key={index}
        type="button"
        className="cite"
        onClick={() => onSelect(citation)}
        aria-label={`Show source ${segment.id}`}
      >
        [{segment.id}]
      </button>
    );
  });
}

/** Render an answer: bullet lines as a list, other lines as paragraphs, citations as buttons. */
function AnswerText({
  message,
  onSelect,
}: {
  message: ChatMessage;
  onSelect: (citation: CitedPassage) => void;
}) {
  return (
    <div className="answer">
      {answerLines(message.content).map((line, index) =>
        line.bullet ? (
          <ul key={index}>
            <li>{renderSegments(line.text, message.citations, onSelect)}</li>
          </ul>
        ) : (
          <p key={index}>{renderSegments(line.text, message.citations, onSelect)}</p>
        ),
      )}
    </div>
  );
}

/** Show the cited passage and a link that opens its page in the stored original. */
function SourcePanel({
  citation,
  base,
  collectionId,
}: {
  citation: CitedPassage;
  base: string;
  collectionId: string;
}) {
  const { passage } = citation;
  return (
    <aside className="source-panel" aria-label="Source">
      <h2>
        Source {citation.source_id}: {passage.filename}
      </h2>
      <p>Page {passage.page}</p>
      <blockquote>{passage.text}</blockquote>
      <a
        href={originalUrl(base, collectionId, passage.document_id, passage.page)}
        target="_blank"
        rel="noopener noreferrer"
      >
        Open page {passage.page} of the original
      </a>
    </aside>
  );
}

export default function ChatPage() {
  const [collectionId, setCollectionId] = useState("");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selected, setSelected] = useState<CitedPassage | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const base = apiBase();

  useEffect(() => {
    setCollectionId(collectionFromUrl());
  }, []);

  useEffect(() => {
    if (!collectionId) {
      return;
    }
    listConversations(base, collectionId)
      .then(setConversations)
      .catch((caught: unknown) =>
        setError(caught instanceof Error ? caught.message : "Could not load conversations."),
      );
  }, [base, collectionId]);

  /** Load a saved conversation into the message list. */
  async function openConversation(conversationId: string): Promise<void> {
    setError(null);
    setSelected(null);
    try {
      const detail = await getConversation(base, collectionId, conversationId);
      setActiveId(detail.id);
      setMessages(detail.messages);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not open the conversation.");
    }
  }

  /** Refresh the history list after a turn finishes. */
  async function refreshList(): Promise<void> {
    setConversations(await listConversations(base, collectionId));
  }

  /** Start an empty conversation. The next question creates it on the server. */
  function startNewChat(): void {
    setActiveId(null);
    setMessages([]);
    setSelected(null);
    setError(null);
  }

  /** Send the draft question and stream the answer into a placeholder message. */
  async function handleSend(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const query = draft.trim();
    if (!query || busy || !collectionId) {
      return;
    }
    const now = new Date().toISOString();
    setBusy(true);
    setError(null);
    setDraft("");
    setMessages((previous) => [
      ...previous,
      { id: PENDING_USER, role: "user", content: query, citations: [], created_at: now },
      { id: PENDING_ASSISTANT, role: "assistant", content: "", citations: [], created_at: now },
    ]);

    let conversationId = activeId;
    let streamed = "";
    try {
      await streamChat(
        base,
        collectionId,
        { query, conversation_id: activeId ?? undefined },
        {
          onConversation: (id) => {
            conversationId = id;
            setActiveId(id);
          },
          onDelta: (text) => {
            streamed += text;
            setMessages((previous) =>
              withMessage(previous, {
                id: PENDING_ASSISTANT,
                role: "assistant",
                content: streamed,
                citations: [],
                created_at: now,
              }),
            );
          },
          onDone: () => undefined,
        },
      );
      if (conversationId) {
        const detail = await getConversation(base, collectionId, conversationId);
        setMessages(detail.messages);
      }
      await refreshList();
    } catch (caught) {
      setMessages((previous) =>
        previous.filter((item) => item.id !== PENDING_USER && item.id !== PENDING_ASSISTANT),
      );
      setDraft(query);
      setError(caught instanceof Error ? caught.message : "The answer could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  if (!collectionId) {
    return (
      <main>
        <h1>Chat</h1>
        <p>
          Open a collection from the <a href="/">collection page</a> to start a chat.
        </p>
      </main>
    );
  }

  return (
    <main className={selected ? "chat-layout with-source" : "chat-layout"}>
      <nav className="chat-sidebar" aria-label="Conversations">
        <a href="/">Back to upload</a>
        <button type="button" onClick={startNewChat} disabled={busy}>
          New chat
        </button>
        <ul>
          {conversations.map((conversation) => (
            <li key={conversation.id}>
              <button
                type="button"
                aria-current={conversation.id === activeId ? "true" : undefined}
                onClick={() => openConversation(conversation.id)}
                disabled={busy}
              >
                {conversation.title}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <section className="chat-main">
        <h1>Ask the collection</h1>
        <div className="messages" aria-live="polite">
          {messages.map((message) => (
            <article key={message.id} className={`message ${message.role}`}>
              <strong>{message.role === "user" ? "You" : "Answer"}</strong>
              {message.role === "assistant" ? (
                <AnswerText message={message} onSelect={setSelected} />
              ) : (
                <p>{message.content}</p>
              )}
            </article>
          ))}
        </div>

        {error ? <p role="alert">{error}</p> : null}

        <form onSubmit={handleSend} className="chat-form">
          <textarea
            aria-label="Question"
            maxLength={2000}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask a question about these documents"
          />
          <button type="submit" disabled={busy || !draft.trim()}>
            {busy ? "Answering..." : "Ask"}
          </button>
        </form>
      </section>

      {selected ? (
        <SourcePanel citation={selected} base={base} collectionId={collectionId} />
      ) : null}
    </main>
  );
}
