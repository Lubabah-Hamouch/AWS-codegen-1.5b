// Incremental parser for the backend's text/event-stream body. EventSource cannot POST, so the stream is read with
// fetch and fed here chunk by chunk; events may be split across chunks at any byte.

export type SSEMessage = { event: string; data: string };

export class SSEParser {
  private buf = "";

  feed(chunk: string): SSEMessage[] {
    this.buf += chunk.replace(/\r\n?/g, "\n");
    const out: SSEMessage[] = [];
    let sep: number;
    while ((sep = this.buf.indexOf("\n\n")) >= 0) {
      const block = this.buf.slice(0, sep);
      this.buf = this.buf.slice(sep + 2);
      const msg = parseBlock(block);
      if (msg) out.push(msg);
    }
    return out;
  }
}

function parseBlock(block: string): SSEMessage | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const i = line.indexOf(":");
    const field = i < 0 ? line : line.slice(0, i);
    let value = i < 0 ? "" : line.slice(i + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length ? { event, data: data.join("\n") } : null;
}
