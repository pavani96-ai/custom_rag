/**
 * Reads the chat stream. The API sends server-sent events (`event:` and `data:` lines, frames
 * separated by a blank line). EventSource cannot send a POST body, so the stream is read with fetch.
 */

import { type ChatMessage, type CitedPassage, errorMessage } from "./api";

export interface StreamEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface ChatDone {
  message_id: string;
  answer: string;
  citations: CitedPassage[];
}

export interface ChatHandlers {
  onConversation: (conversationId: string) => void;
  onDelta: (text: string) => void;
  onDone: (done: ChatDone) => void;
}

/** Parse one frame into an event. Returns null for frames without data or with bad JSON. */
export function parseFrame(frame: string): StreamEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) {
      event = line.slice("event: ".length);
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice("data: ".length));
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) as Record<string, unknown> };
  } catch {
    return null;
  }
}

/** Split buffered text into complete events. The unfinished tail is returned as `rest`. */
export function parseFrames(buffer: string): { events: StreamEvent[]; rest: string } {
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  const events = frames
    .map(parseFrame)
    .filter((event): event is StreamEvent => event !== null);
  return { events, rest };
}

/** Send one event to the matching handler. An `error` event becomes a thrown Error. */
export function dispatchEvent(event: StreamEvent, handlers: ChatHandlers): void {
  const { data } = event;
  if (event.event === "conversation") {
    handlers.onConversation(String(data.conversation_id));
  } else if (event.event === "delta") {
    handlers.onDelta(String(data.text ?? ""));
  } else if (event.event === "done") {
    handlers.onDone(data as unknown as ChatDone);
  } else if (event.event === "error") {
    throw new Error(String(data.detail ?? "The answer could not be completed."));
  }
}

/** Ask one question and stream the answer. Resolves after the stream ends. */
export async function streamChat(
  base: string,
  collectionId: string,
  body: { query: string; conversation_id?: string },
  handlers: ChatHandlers,
): Promise<void> {
  const response = await fetch(`${base}/collections/${collectionId}/chat/stream`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    throw new Error(await errorMessage(response));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseFrames(buffer);
    buffer = parsed.rest;
    parsed.events.forEach((event) => dispatchEvent(event, handlers));
  }
  parseFrames(`${buffer}\n\n`).events.forEach((event) => dispatchEvent(event, handlers));
}

/** Return a copy of the messages with the message that has this ID replaced. */
export function withMessage(messages: ChatMessage[], message: ChatMessage): ChatMessage[] {
  return messages.map((item) => (item.id === message.id ? message : item));
}
