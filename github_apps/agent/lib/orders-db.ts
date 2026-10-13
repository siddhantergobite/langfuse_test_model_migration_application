import { mkdirSync, readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import path from "node:path";
import sampleOrders from "@/data/demo_orders.json";

export interface DemoOrder {
  id: string;
  customer_id: string;
  date: string;
  status: string;
  product: string;
  total: number;
}

const databaseCache = globalThis as typeof globalThis & {
  __supportDemoDatabase?: DatabaseSync;
};

function getDatabase(): DatabaseSync {
  if (databaseCache.__supportDemoDatabase) {
    return databaseCache.__supportDemoDatabase;
  }

  const projectRoot = process.cwd();
  const dataDirectory = path.join(projectRoot, "data");
  mkdirSync(dataDirectory, { recursive: true });

  const database = new DatabaseSync(
    path.join(dataDirectory, "support_demo.sqlite")
  );

  database.exec(readFileSync(path.join(dataDirectory, "schema.sql"), "utf8"));
  const row = database
    .prepare("SELECT COUNT(*) AS count FROM demo_orders")
    .get() as { count: number };

  if (row.count === 0) {
    const insert = database.prepare(
      `INSERT INTO demo_orders (id, customer_id, date, status, product, total)
       VALUES (?, ?, ?, ?, ?, ?)`
    );
    database.exec("BEGIN");
    try {
      for (const order of sampleOrders as DemoOrder[]) {
        insert.run(
          order.id,
          order.customer_id,
          order.date,
          order.status,
          order.product,
          order.total
        );
      }
      database.exec("COMMIT");
    } catch (error) {
      database.exec("ROLLBACK");
      database.close();
      throw error;
    }
  }

  databaseCache.__supportDemoDatabase = database;
  return database;
}

export function getDemoOrders(customerId?: string): DemoOrder[] {
  const database = getDatabase();
  const rows = customerId
    ? database
        .prepare(
          `SELECT id, customer_id, date, status, product, total
           FROM demo_orders WHERE customer_id = ? ORDER BY date DESC, id`
        )
        .all(customerId)
    : database
        .prepare(
          `SELECT id, customer_id, date, status, product, total
           FROM demo_orders ORDER BY date DESC, id`
        )
        .all();

  return rows as DemoOrder[];
}

export function getDemoOrder(orderId: string): DemoOrder | null {
  const row = getDatabase()
    .prepare(
      `SELECT id, customer_id, date, status, product, total
       FROM demo_orders WHERE id = ? COLLATE NOCASE`
    )
    .get(orderId.trim()) as DemoOrder | undefined;

  return row ?? null;
}
