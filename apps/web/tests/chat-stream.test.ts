/**
 * Unit tests for the chat stream parser and answer splitting. Run with `npm test`.
 * No network calls are made.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { dispatchEvent, parseFrames, withMessage } from "../lib/chat-stream";
import { answerLines, splitCitations } from "../lib/citations";

test("complete frames become events and an unfinished tail is kept", () => {
  const buffer =
    'event: delta\ndata: {"text": "Hi [1]"}\n\nevent: delta\ndata: {"text": "more"}';
  const { events, rest } = parseFrames(buffer);
  assert.equal(events.length, 1);
  assert.equal(events[0].event, "delta");
  assert.deepEqual(events[0].data, { text: "Hi [1]" });
  assert.equal(rest, 'event: delta\ndata: {"text": "more"}');
});

test("a frame split across reads is parsed once it completes", () => {
  const first = parseFrames('event: delta\ndata: {"te');
  assert.equal(first.events.length, 0);
  const second = parseFrames(`${first.rest}xt": "ok"}\n\n`);
  assert.deepEqual(second.events[0].data, { text: "ok" });
});

test("a frame with bad JSON is skipped without stopping the stream", () => {
  const { events } = parseFrames('event: delta\ndata: {bad\n\nevent: delta\ndata: {"text":"a"}\n\n');
  assert.equal(events.length, 1);
  assert.deepEqual(events[0].data, { text: "a" });
});

test("an error event throws the server's safe message", () => {
  const handlers = { onConversation() {}, onDelta() {}, onDone() {} };
  assert.throws(
    () =>
      dispatchEvent(
        { event: "error", data: { detail: "Gemini generation is unavailable." } },
        handlers,
      ),
    /Gemini generation is unavailable/,
  );
});

test("done and delta events reach their handlers", () => {
  const seen: string[] = [];
  const handlers = {
    onConversation: (id: string) => seen.push(`conversation:${id}`),
    onDelta: (text: string) => seen.push(`delta:${text}`),
    onDone: (done: { message_id: string }) => seen.push(`done:${done.message_id}`),
  };
  dispatchEvent({ event: "conversation", data: { conversation_id: "c1" } }, handlers);
  dispatchEvent({ event: "delta", data: { text: "x" } }, handlers);
  dispatchEvent({ event: "done", data: { message_id: "m1" } }, handlers);
  assert.deepEqual(seen, ["conversation:c1", "delta:x", "done:m1"]);
});

test("splitCitations keeps text order and turns markers into citation segments", () => {
  assert.deepEqual(splitCitations("A [1] and B [2]."), [
    { kind: "text", text: "A " },
    { kind: "cite", id: 1 },
    { kind: "text", text: " and B " },
    { kind: "cite", id: 2 },
    { kind: "text", text: "." },
  ]);
  assert.deepEqual(splitCitations("Both [1, 2]."), [
    { kind: "text", text: "Both " },
    { kind: "cite", id: 1 },
    { kind: "text", text: ", " },
    { kind: "cite", id: 2 },
    { kind: "text", text: "." },
  ]);
  assert.deepEqual(splitCitations("No markers."), [{ kind: "text", text: "No markers." }]);
});

test("withMessage replaces only the matching message", () => {
  const base = { role: "assistant" as const, citations: [], created_at: "t" };
  const messages = [
    { ...base, id: "a", content: "old" },
    { ...base, id: "b", content: "keep" },
  ];
  const updated = withMessage(messages, { ...base, id: "a", content: "new" });
  assert.equal(updated[0].content, "new");
  assert.equal(updated[1].content, "keep");
});

test("answerLines marks bullet lines and drops the markers", () => {
  assert.deepEqual(answerLines("* One [1]\n- Two [2]\n\nPlain line."), [
    { bullet: true, text: "One [1]" },
    { bullet: true, text: "Two [2]" },
    { bullet: false, text: "Plain line." },
  ]);
});
