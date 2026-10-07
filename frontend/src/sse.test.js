import test from "node:test";
import assert from "node:assert/strict";
import { readChatEvents } from "./sse.js";

function body(text, size = 1) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      for (let offset = 0; offset < bytes.length; offset += size) {
        controller.enqueue(bytes.slice(offset, offset + size));
      }
      controller.close();
    },
  });
}

test("reads split UTF-8 events, CRLF frames and heartbeat comments", async () => {
  const events = [];
  const stream = ': keep-alive\r\n\r\nevent: start\r\ndata: {"thread_id":"t"}\r\n\r\n' +
    'event: delta\ndata: {"text":"Xin "}\n\nevent: delta\ndata: {"text":"chào 🌏\\nNext"}\n\n' +
    'event: result\ndata: {"answer":"Xin chào 🌏\\nNext"}\n\n';
  const result = await readChatEvents(body(stream), (event, data) => events.push([event, data]));
  assert.equal(result.answer, "Xin chào 🌏\nNext");
  assert.deepEqual(events.map(([event]) => event), ["start", "delta", "delta", "result"]);
  assert.equal(events.filter(([event]) => event === "delta").map(([, data]) => data.text).join(""), result.answer);
});

test("reports server error events", async () => {
  await assert.rejects(readChatEvents(body('event: error\ndata: {"detail":"Try again"}\n\n')), /Try again/);
});

test("rejects streams that end without a final result", async () => {
  await assert.rejects(readChatEvents(body('event: start\ndata: {}\n\n')), /ended before/);
});
