import { describe, expect, it } from "vitest";
import { createLatestRequestGate } from "./latestRequestGate";

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolvePromise: ((value: T) => void) | undefined;
  const promise = new Promise<T>((resolve) => {
    resolvePromise = resolve;
  });
  return {
    promise,
    resolve(value: T): void {
      if (!resolvePromise) throw new Error("Deferred promise is unavailable");
      resolvePromise(value);
    },
  };
}

describe("createLatestRequestGate", () => {
  it("discards a slower response after a newer selection has started", async () => {
    const gate = createLatestRequestGate();
    const first = deferred<number>();
    const second = deferred<number>();
    const applied: number[] = [];

    async function applyLatest(source: Promise<number>): Promise<void> {
      const requestId = gate.begin();
      const value = await source;
      if (gate.isCurrent(requestId)) applied.push(value);
    }

    const firstRequest = applyLatest(first.promise);
    const secondRequest = applyLatest(second.promise);
    second.resolve(22);
    await secondRequest;
    first.resolve(21);
    await firstRequest;

    expect(applied).toEqual([22]);
  });

  it("invalidates an in-flight detail request when the version list refreshes", () => {
    const gate = createLatestRequestGate();
    const requestId = gate.begin();
    gate.invalidate();
    expect(gate.isCurrent(requestId)).toBe(false);
  });
});
