#!/usr/bin/env node

import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import * as z from "zod/v4";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DEFAULT_TIMEOUT_MS = 30_000;

const OrderSideSchema = z.enum(["buy", "sell"]);
const OrderTypeSchema = z.enum(["market", "limit"]);
const OrderStatusSchema = z.enum(["open", "filled", "canceled", "rejected", "unknown"]);

function envBool(name, fallback) {
  const value = process.env[name];
  if (value == null || value === "") return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function jsonResult(data, isError = false) {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(data, null, 2),
      },
    ],
    structuredContent: data,
    isError,
  };
}

function maskAccountId(value) {
  if (!value) return undefined;
  if (value.length <= 4) return "****";
  return `${value.slice(0, 2)}****${value.slice(-2)}`;
}

function getBaseBrokerStatus(extra = {}) {
  const qmtUserdataPath = process.env.QMT_USERDATA_PATH;
  const accountId = process.env.QMT_ACCOUNT_ID;
  const liveTradingEnabled = envBool("QMT_ENABLE_LIVE_TRADING", false);
  const requireConfirmation = envBool("QMT_REQUIRE_CONFIRMATION", true);

  return {
    connectorType: "live",
    provider: "qmt",
    tradingMode: liveTradingEnabled ? "live" : "dry_run_only",
    configured: Boolean(qmtUserdataPath && accountId),
    connected: undefined,
    liveTradingEnabled,
    requireConfirmation,
    account: {
      accountId: maskAccountId(accountId),
      accountType: process.env.QMT_ACCOUNT_TYPE || "STOCK",
      qmtUserdataPathConfigured: Boolean(qmtUserdataPath),
      pythonCommand: process.env.QMT_PYTHON || "python3",
    },
    capabilities: [
      "broker_status",
      "dry_run_order",
      "place_order",
      "cancel_order",
      "query_orders",
      "query_positions",
      "query_cash",
    ],
    safety: {
      realOrders: liveTradingEnabled,
      requiresExplicitConfirmation: requireConfirmation,
      note: "Real QMT orders require QMT_ENABLE_LIVE_TRADING=true and confirmed=true when confirmation is enabled.",
    },
    ...extra,
  };
}

class QmtWorker {
  constructor() {
    this.nextId = 1;
    this.pending = new Map();
    this.buffer = "";
    this.process = undefined;
  }

  start() {
    if (this.process) return;

    const pythonCommand = process.env.QMT_PYTHON || "python3";
    this.process = spawn(pythonCommand, [join(__dirname, "qmt_worker.py")], {
      env: process.env,
      stdio: ["pipe", "pipe", "pipe"],
    });

    this.process.stdout.setEncoding("utf8");
    this.process.stdout.on("data", (chunk) => this.handleStdout(chunk));
    this.process.stderr.setEncoding("utf8");
    this.process.stderr.on("data", (chunk) => {
      process.stderr.write(`[qmt-broker-worker] ${chunk}`);
    });
    this.process.on("exit", (code, signal) => {
      const error = new Error(`QMT worker exited with code=${code} signal=${signal}`);
      for (const pending of this.pending.values()) {
        clearTimeout(pending.timeout);
        pending.reject(error);
      }
      this.pending.clear();
      this.process = undefined;
    });
  }

  handleStdout(chunk) {
    this.buffer += chunk;
    for (;;) {
      const newlineIndex = this.buffer.indexOf("\n");
      if (newlineIndex < 0) break;

      const line = this.buffer.slice(0, newlineIndex).trim();
      this.buffer = this.buffer.slice(newlineIndex + 1);
      if (!line) continue;

      let message;
      try {
        message = JSON.parse(line);
      } catch (error) {
        process.stderr.write(`[qmt-broker-worker] invalid json: ${line}\n`);
        continue;
      }

      const pending = this.pending.get(message.id);
      if (!pending) continue;
      this.pending.delete(message.id);
      clearTimeout(pending.timeout);

      if (message.error) {
        pending.reject(new Error(message.error));
      } else {
        pending.resolve(message.result);
      }
    }
  }

  call(method, params = {}) {
    this.start();

    const id = this.nextId++;
    const timeoutMs = Number(process.env.QMT_REQUEST_TIMEOUT_MS || DEFAULT_TIMEOUT_MS);
    const payload = JSON.stringify({ id, method, params });

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`QMT worker request timed out: ${method}`));
      }, Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : DEFAULT_TIMEOUT_MS);

      this.pending.set(id, { resolve, reject, timeout });
      this.process.stdin.write(`${payload}\n`, (error) => {
        if (!error) return;
        this.pending.delete(id);
        clearTimeout(timeout);
        reject(error);
      });
    });
  }

  close() {
    if (!this.process) return;
    this.process.kill();
  }
}

const baseOrderInput = {
  symbol: z.string().min(1).describe("Trading symbol, for example 600519.SH or 000001.SZ."),
  side: OrderSideSchema.describe("Order side."),
  quantity: z.number().positive().describe("Order quantity. A-share stocks usually require board-lot sizing."),
  orderType: OrderTypeSchema.describe("Order type."),
  limitPrice: z.number().positive().optional().describe("Required for limit orders."),
  referencePrice: z
    .number()
    .positive()
    .optional()
    .describe("Used by dry-run for market orders when no quote feed is available."),
};

function registerTools(server, worker) {
  server.registerTool(
    "broker_status",
    {
      title: "Get QMT broker status",
      description:
        "Return QMT configuration, live-trading safety state, available capabilities, and optionally check the MiniQMT connection.",
      inputSchema: {
        checkConnection: z
          .boolean()
          .optional()
          .describe("When true, also starts the Python worker and checks MiniQMT connectivity."),
      },
    },
    async (input) => {
      if (input.checkConnection !== true) {
        return jsonResult(getBaseBrokerStatus());
      }

      try {
        return jsonResult(await worker.call("broker_status", input));
      } catch (error) {
        return jsonResult(
          getBaseBrokerStatus({
            connected: false,
            reason: error instanceof Error ? error.message : String(error),
          }),
        );
      }
    },
  );

  server.registerTool(
    "dry_run_order",
    {
      title: "Dry run QMT order",
      description: "Validate an order against QMT account cash/position without submitting it.",
      inputSchema: baseOrderInput,
    },
    async (input) => jsonResult(await worker.call("dry_run_order", input)),
  );

  server.registerTool(
    "place_order",
    {
      title: "Place QMT live order",
      description:
        "Submit a real QMT order. Requires QMT_ENABLE_LIVE_TRADING=true and confirmed=true by default.",
      inputSchema: {
        ...baseOrderInput,
        clientOrderId: z.string().optional().describe("Client-side idempotency key or trace id."),
        confirmed: z.boolean().optional().describe("Must be true after explicit user confirmation."),
        strategyName: z.string().optional().describe("QMT strategy name."),
        orderRemark: z.string().optional().describe("QMT order remark for audit and tracing."),
      },
    },
    async (input) => {
      if (!envBool("QMT_ENABLE_LIVE_TRADING", false)) {
        return jsonResult(
          {
            accepted: false,
            reason:
              "Live trading is disabled. Set QMT_ENABLE_LIVE_TRADING=true only after QMT account, permissions, and risk controls are verified.",
          },
          true,
        );
      }

      if (envBool("QMT_REQUIRE_CONFIRMATION", true) && input.confirmed !== true) {
        return jsonResult(
          {
            accepted: false,
            reason: "place_order requires confirmed=true after explicit user confirmation.",
          },
          true,
        );
      }

      return jsonResult(await worker.call("place_order", input));
    },
  );

  server.registerTool(
    "cancel_order",
    {
      title: "Cancel QMT order",
      description: "Cancel an open QMT order.",
      inputSchema: {
        orderId: z.string().min(1).describe("QMT order id."),
      },
    },
    async (input) => jsonResult(await worker.call("cancel_order", input)),
  );

  server.registerTool(
    "query_orders",
    {
      title: "Query QMT orders",
      description: "Query current-day QMT orders.",
      inputSchema: {
        status: OrderStatusSchema.optional().describe("Best-effort normalized status filter."),
        symbol: z.string().optional().describe("Filter by trading symbol."),
      },
    },
    async (input) => jsonResult(await worker.call("query_orders", input)),
  );

  server.registerTool(
    "query_positions",
    {
      title: "Query QMT positions",
      description: "Query QMT stock positions.",
      inputSchema: {
        symbol: z.string().optional().describe("Filter by trading symbol."),
      },
    },
    async (input) => jsonResult(await worker.call("query_positions", input)),
  );

  server.registerTool(
    "query_cash",
    {
      title: "Query QMT cash",
      description: "Query QMT account cash and asset summary.",
      inputSchema: {},
    },
    async () => jsonResult(await worker.call("query_cash")),
  );
}

async function main() {
  const transportArgIndex = process.argv.indexOf("--transport");
  const transport = transportArgIndex >= 0 ? process.argv[transportArgIndex + 1] : "stdio";

  if (transport !== "stdio") {
    throw new Error(`Unsupported transport "${transport}". Only stdio is supported.`);
  }

  const worker = new QmtWorker();
  const server = new McpServer({
    name: "qmt-broker-mcp",
    version: "0.1.0",
  });

  registerTools(server, worker);
  process.on("exit", () => worker.close());

  await server.connect(new StdioServerTransport());
}

main().catch((error) => {
  console.error("[qmt-broker-mcp] fatal error", error);
  process.exit(1);
});
