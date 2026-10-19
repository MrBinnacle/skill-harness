/**
 * skill-harness Pi capture extension — evidence capture ONLY.
 *
 * This extension's sole purpose is to persist what the Pi runtime presented
 * and did during one paired-lane epoch. It registers no tools, no commands,
 * no shortcuts, and no flags. Every handler is notification-only: none of
 * them return a value, mutate an event object, or touch the request path.
 * In particular the before_provider_request handler returns undefined, so
 * the payload is sent exactly as built.
 *
 * Capture is best-effort at the extension and fail-closed at the parser: a
 * missing or partial capture directory makes the epoch unparseable
 * (skill_harness.subject.pi.parser), never quietly admissible.
 *
 * Layout under $PI_CAPTURE_DIR:
 *   session_start.json        session file path, cwd, mode
 *   agent_start.json          systemPromptOptions (roster!), system prompt,
 *                             model, thinking level
 *   requests/request-NNN.json serialized provider payload, per request, in
 *                             order; request-001 is the mandatory first one
 *   events.jsonl              tool executions, raw input (for /skill:
 *                             expansion detection), model/thinking changes,
 *                             lifecycle markers
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export default function (pi: ExtensionAPI) {
  const dir = process.env.PI_CAPTURE_DIR;
  if (!dir) {
    throw new Error("PI_CAPTURE_DIR is not set; refusing to run an epoch without capture");
  }
  mkdirSync(join(dir, "requests"), { recursive: true });

  let requestCount = 0;

  const logEvent = (name: string, data: unknown) => {
    appendFileSync(
      join(dir, "events.jsonl"),
      JSON.stringify({ t: new Date().toISOString(), name, data }) + "\n",
    );
  };

  pi.on("session_start", async (_event, ctx) => {
    writeFileSync(
      join(dir, "session_start.json"),
      JSON.stringify(
        {
          sessionFile: ctx.sessionManager.getSessionFile() ?? null,
          cwd: ctx.cwd,
          mode: ctx.mode,
        },
        null,
        2,
      ),
    );
  });

  pi.on("before_agent_start", async (event, ctx) => {
    writeFileSync(
      join(dir, "agent_start.json"),
      JSON.stringify(
        {
          model: ctx.model
            ? { provider: ctx.model.provider, id: ctx.model.id }
            : null,
          thinkingLevel: ctx.thinkingLevel,
          systemPrompt: event.systemPrompt,
          systemPromptOptions: (event as any).systemPromptOptions ?? null,
        },
        null,
        2,
      ),
    );
    logEvent("before_agent_start", { systemPromptLen: event.systemPrompt.length });
  });

  pi.on("before_provider_request", (event: any) => {
    requestCount += 1;
    const name = `request-${String(requestCount).padStart(3, "0")}.json`;
    writeFileSync(
      join(dir, "requests", name),
      JSON.stringify(
        {
          t: new Date().toISOString(),
          index: requestCount,
          payload: event.payload,
        },
        null,
        2,
      ),
    );
  });

  pi.on("input", async (event: any) => {
    // Raw user input BEFORE /skill: expansion — the definitive record of an
    // explicit skill invocation. Read-only observation; the event continues.
    logEvent("input", { text: event.text, source: event.source });
  });

  pi.on("tool_execution_start", async (event: any) => {
    logEvent("tool_execution_start", {
      toolCallId: event.toolCallId,
      tool: event.toolName,
      args: event.args,
    });
  });

  pi.on("tool_execution_end", async (event: any) => {
    logEvent("tool_execution_end", {
      toolCallId: event.toolCallId,
      tool: event.toolName,
      isError: event.isError,
    });
  });

  pi.on("model_select", async (event: any) => {
    logEvent("model_select", {
      model: event.model?.id ?? null,
      provider: event.model?.provider ?? null,
      source: event.source,
    });
  });

  pi.on("thinking_level_select", async (event: any) => {
    logEvent("thinking_level_select", {
      level: event.level,
      previousLevel: event.previousLevel,
    });
  });

  pi.on("turn_end", async (event: any) => {
    logEvent("turn_end", { turnIndex: event.turnIndex });
  });

  pi.on("agent_end", async () => {
    logEvent("agent_end", {});
  });

  pi.on("session_shutdown", async (event: any) => {
    logEvent("session_shutdown", { reason: event.reason });
  });
}
