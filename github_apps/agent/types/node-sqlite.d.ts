declare module "node:sqlite" {
  type SQLInputValue = string | number | bigint | null | Uint8Array;

  interface StatementSync {
    all(...values: SQLInputValue[]): unknown[];
    get(...values: SQLInputValue[]): unknown;
    run(...values: SQLInputValue[]): unknown;
  }

  export class DatabaseSync {
    constructor(path: string);
    exec(sql: string): void;
    prepare(sql: string): StatementSync;
    close(): void;
  }
}
