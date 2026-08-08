#!/usr/bin/env node

import { randomUUID } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import * as z from "zod/v4";

const DEFAULT_INITIAL_CASH = 100000;
const DEFAULT_CURRENCY = "USD";
const DEFAULT_MARKET = "SIM";

const OrderSideSchema = z.enum(["buy", "sell"]);
const OrderTypeSchema = z.enum(["market", "limit"]);
const OrderStatusSchema = z.enum(["open", "filled", "canceled", "rejected"]);

function envBool(name, fallback) {
  const value = process.env[name];
  if (value == null || value === "") return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function envNumber(name, fallback) {
  const raw = process.env[name];
  if (raw == null || raw === "") return fallback;

  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function normalizeSymbol(symbol) {
  return symbol.trim().toUpperCase();
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

function createState() {
  return {
    cash: envNumber("PAPER_BROKER_INITIAL_CASH", DEFAULT_INITIAL_CASH),
    currency: process.env.PAPER_BROKER_CURRENCY || DEFAULT_CURRENCY,
    market: process.env.PAPER_BROKER_MARKET || DEFAULT_MARKET,
    allowShort: envBool("PAPER_BROKER_ALLOW_SHORT", false),
    requireConfirmation: envBool("PAPER_BROKER_REQUIRE_CONFIRMATION", true),
    positions: new Map(),
    orders: [],
  };
}

function getBrokerStatus(state) {
  return {
    connectorType: "paper",
    provider: "paper-broker",
    tradingMode: "simulation",
    configured: true,
    connected: true,
    liveTradingEnabled: false,
    requireConfirmation: state.requireConfirmation,
    account: {
      market: state.market,
      currency: state.currency,
      cash: state.cash,
      available: state.cash,
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
      realOrders: false,
      requiresExplicitConfirmation: state.requireConfirmation,
      note: "This connector never submits real broker orders.",
    },
  };
}

function getPosition(state, symbol) {
  const existing = state.positions.get(symbol);
  if (existing) return existing;

  const position = {
    symbol,
    market: state.market,
    quantity: 0,
    averageCost: 0,
  };
  state.positions.set(symbol, position);
  return position;
}

function resolvePrice(input) {
  if (input.orderType === "limit") {
    if (typeof input.limitPrice !== "number" || input.limitPrice <= 0) {
      return {
        ok: false,
        reason: "limitPrice is required for limit orders and must be greater than 0.",
      };
    }

    return { ok: true, price: input.limitPrice };
  }

  if (typeof input.referencePrice !== "number" || input.referencePrice <= 0) {
    return {
      ok: false,
      reason: "referencePrice is required for market orders because this paper broker has no live quote feed.",
    };
  }

  return { ok: true, price: input.referencePrice };
}

function estimateOrder(state, input) {
  const symbol = normalizeSymbol(input.symbol);
  const quantity = Number(input.quantity);

  if (!Number.isFinite(quantity) || quantity <= 0) {
    return {
      accepted: false,
      reason: "quantity must be greater than 0.",
      symbol,
    };
  }

  const priceResult = resolvePrice(input);
  if (!priceResult.ok) {
    return {
      accepted: false,
      reason: priceResult.reason,
      symbol,
    };
  }

  const position = getPosition(state, symbol);
  const gross = Number((priceResult.price * quantity).toFixed(8));
  const cashImpact = input.side === "buy" ? -gross : gross;
  const positionImpact = input.side === "buy" ? quantity : -quantity;

  if (input.side === "buy" && state.cash + cashImpact < 0) {
    return {
      accepted: false,
      reason: "insufficient available cash.",
      symbol,
      price: priceResult.price,
      estimatedCashImpact: cashImpact,
      estimatedPositionImpact: positionImpact,
    };
  }

  if (!state.allowShort && input.side === "sell" && position.quantity < quantity) {
    return {
      accepted: false,
      reason: "insufficient position for sell order; short selling is disabled.",
      symbol,
      price: priceResult.price,
      estimatedCashImpact: cashImpact,
      estimatedPositionImpact: positionImpact,
    };
  }

  return {
    accepted: true,
    symbol,
    price: priceResult.price,
    estimatedCashImpact: cashImpact,
    estimatedPositionImpact: positionImpact,
    estimatedGrossAmount: gross,
  };
}

function applyFilledOrder(state, input, estimate) {
  const position = getPosition(state, estimate.symbol);
  const previousQuantity = position.quantity;
  const nextQuantity = previousQuantity + estimate.estimatedPositionImpact;

  state.cash = Number((state.cash + estimate.estimatedCashImpact).toFixed(8));

  if (input.side === "buy") {
    const previousCost = previousQuantity * position.averageCost;
    const addedCost = input.quantity * estimate.price;
    position.averageCost = Number(
      ((previousCost + addedCost) / nextQuantity).toFixed(8),
    );
  }

  position.quantity = Number(nextQuantity.toFixed(8));
  if (position.quantity === 0) {
    position.averageCost = 0;
  }
}

const baseOrderInput = {
  symbol: z.string().min(1).describe("Trading symbol, for example AAPL, 600519, BTCUSDT."),
  side: OrderSideSchema.describe("Order side."),
  quantity: z.number().positive().describe("Order quantity."),
  orderType: OrderTypeSchema.describe("Order type."),
  limitPrice: z.number().positive().optional().describe("Required for limit orders."),
  referencePrice: z
    .number()
    .positive()
    .optional()
    .describe("Required for market orders because the paper broker has no quote feed."),
};

function registerTools(server, state) {
  server.registerTool(
    "broker_status",
    {
      title: "Get paper broker status",
      description:
        "Return simulated broker mode, account state, available capabilities, and safety constraints.",
      inputSchema: {},
    },
    async () => jsonResult(getBrokerStatus(state)),
  );

  server.registerTool(
    "dry_run_order",
    {
      title: "Dry run order",
      description: "Validate an order and estimate cash/position impact without submitting it.",
      inputSchema: baseOrderInput,
    },
    async (input) => {
      const estimate = estimateOrder(state, input);
      return jsonResult({
        ...estimate,
        currency: state.currency,
        market: state.market,
        availableCash: state.cash,
      });
    },
  );

  server.registerTool(
    "place_order",
    {
      title: "Place paper order",
      description:
        "Submit a simulated paper order. Requires confirmed=true by default; this server never sends real broker orders.",
      inputSchema: {
        ...baseOrderInput,
        clientOrderId: z.string().optional().describe("Client-provided order id for idempotency."),
        confirmed: z
          .boolean()
          .optional()
          .describe("Must be true after explicit user confirmation unless disabled by server config."),
        fillMode: z
          .enum(["immediate", "open"])
          .optional()
          .describe("immediate fills the order now; open records a cancelable open order."),
      },
    },
    async (input) => {
      if (state.requireConfirmation && input.confirmed !== true) {
        return jsonResult(
          {
            accepted: false,
            reason: "place_order requires confirmed=true after explicit user confirmation.",
          },
          true,
        );
      }

      const estimate = estimateOrder(state, input);
      const now = new Date().toISOString();
      const order = {
        orderId: randomUUID(),
        clientOrderId: input.clientOrderId,
        symbol: estimate.symbol ?? normalizeSymbol(input.symbol),
        side: input.side,
        quantity: input.quantity,
        orderType: input.orderType,
        limitPrice: input.limitPrice,
        referencePrice: input.referencePrice,
        price: estimate.price,
        status: estimate.accepted ? "open" : "rejected",
        submittedAt: now,
        updatedAt: now,
        reason: estimate.reason,
        estimatedCashImpact: estimate.estimatedCashImpact,
        estimatedPositionImpact: estimate.estimatedPositionImpact,
      };

      if (estimate.accepted && (input.fillMode ?? "immediate") === "immediate") {
        applyFilledOrder(state, input, estimate);
        order.status = "filled";
        order.filledAt = now;
      }

      state.orders.push(order);
      return jsonResult(order, !estimate.accepted);
    },
  );

  server.registerTool(
    "cancel_order",
    {
      title: "Cancel paper order",
      description: "Cancel an open simulated paper order.",
      inputSchema: {
        orderId: z.string().min(1).describe("Order id returned by place_order."),
      },
    },
    async ({ orderId }) => {
      const order = state.orders.find((item) => item.orderId === orderId);
      if (!order) {
        return jsonResult({ orderId, status: "not_found" }, true);
      }

      if (order.status !== "open") {
        return jsonResult({
          orderId,
          status: order.status,
          reason: "Only open orders can be canceled.",
        });
      }

      order.status = "canceled";
      order.updatedAt = new Date().toISOString();
      return jsonResult({
        orderId,
        status: order.status,
      });
    },
  );

  server.registerTool(
    "query_orders",
    {
      title: "Query paper orders",
      description: "Query simulated paper orders by status or symbol.",
      inputSchema: {
        status: OrderStatusSchema.optional().describe("Filter by order status."),
        symbol: z.string().optional().describe("Filter by trading symbol."),
      },
    },
    async ({ status, symbol }) => {
      const normalizedSymbol = symbol ? normalizeSymbol(symbol) : undefined;
      const orders = state.orders.filter((order) => {
        if (status && order.status !== status) return false;
        if (normalizedSymbol && order.symbol !== normalizedSymbol) return false;
        return true;
      });

      return jsonResult({ orders });
    },
  );

  server.registerTool(
    "query_positions",
    {
      title: "Query paper positions",
      description: "Query simulated paper positions.",
      inputSchema: {
        symbol: z.string().optional().describe("Filter by trading symbol."),
      },
    },
    async ({ symbol }) => {
      const normalizedSymbol = symbol ? normalizeSymbol(symbol) : undefined;
      const positions = Array.from(state.positions.values()).filter((position) => {
        if (position.quantity === 0) return false;
        if (normalizedSymbol && position.symbol !== normalizedSymbol) return false;
        return true;
      });

      return jsonResult({ positions });
    },
  );

  server.registerTool(
    "query_cash",
    {
      title: "Query paper cash",
      description: "Query simulated cash balance.",
      inputSchema: {},
    },
    async () =>
      jsonResult({
        cash: state.cash,
        currency: state.currency,
        available: state.cash,
        market: state.market,
      }),
  );
}

async function main() {
  const transportArgIndex = process.argv.indexOf("--transport");
  const transport = transportArgIndex >= 0 ? process.argv[transportArgIndex + 1] : "stdio";

  if (transport !== "stdio") {
    throw new Error(`Unsupported transport "${transport}". Only stdio is supported.`);
  }

  const state = createState();
  const server = new McpServer({
    name: "paper-broker-mcp",
    version: "0.1.0",
  });

  registerTools(server, state);

  await server.connect(new StdioServerTransport());
}

main().catch((error) => {
  console.error("[paper-broker-mcp] fatal error", error);
  process.exit(1);
});
