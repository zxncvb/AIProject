export function parseAgentSseFrames(buffer, flush = false) {
  const frames = buffer.split(/\r?\n\r?\n/);
  if (!flush) buffer = frames.pop() || "";
  return {
    buffer: flush ? "" : buffer,
    events: frames.filter((frame) => frame.trim()).map((frame) => {
      const eventName = frame.match(/^event:\s*(.+)$/m)?.[1]?.trim() || "message";
      const data = frame.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
      if (!data) return { event: eventName, payload: {} };
      try { return { event: eventName, payload: JSON.parse(data) }; } catch { return { event: eventName, payload: { message: data } }; }
    }),
  };
}
