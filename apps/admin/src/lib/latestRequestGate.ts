export interface LatestRequestGate {
  begin: () => number;
  invalidate: () => void;
  isCurrent: (requestId: number) => boolean;
}

export function createLatestRequestGate(): LatestRequestGate {
  let sequence = 0;
  return {
    begin(): number {
      sequence += 1;
      return sequence;
    },
    invalidate(): void {
      sequence += 1;
    },
    isCurrent(requestId: number): boolean {
      return requestId === sequence;
    },
  };
}
