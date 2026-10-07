// Read POST SSE responses while retaining support for bearer-token headers.
export async function readChatEvents(body, onEvent = () => {}) {
  if (!body) throw new Error("Streaming response is unavailable");
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        let event = "message";
        const lines = [];
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) lines.push(line.slice(5).replace(/^ /, ""));
        }
        if (!lines.length) continue; // Heartbeat comments.
        const data = JSON.parse(lines.join("\n"));
        if (event === "error") throw new Error(data.detail || "Chat stream failed");
        onEvent(event, data);
        if (event === "result") return data;
      }
      if (done) throw new Error("Chat stream ended before a response was received");
    }
  } finally {
    try { await reader.cancel(); } finally { reader.releaseLock(); }
  }
}
