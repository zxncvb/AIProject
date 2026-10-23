import assert from "node:assert/strict";
import test from "node:test";

import { parseAgentSseFrames } from "../src/agent_stream.js";

test("reassembles split SSE frames and preserves unfinished data", () => {
  const first = parseAgentSseFrames('event: token\ndata: {"text":"你"}\n\nevent: tool_call\ndata: {"name":"lookup"}\n\npartial');
  assert.equal(first.buffer, "partial");
  assert.deepEqual(first.events, [
    { event: "token", payload: { text: "你" } },
    { event: "tool_call", payload: { name: "lookup" } },
  ]);

  const last = parseAgentSseFrames('event: done\ndata: {"text":"完成"}', true);
  assert.deepEqual(last.events, [{ event: "done", payload: { text: "完成" } }]);
  assert.equal(last.buffer, "");
});

test("supports CRLF and multiline data fields", () => {
  const result = parseAgentSseFrames("event: error\r\ndata: first\r\ndata: second\r\n\r\n");
  assert.deepEqual(result.events, [{ event: "error", payload: { message: "first\nsecond" } }]);
});
