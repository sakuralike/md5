import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

class TestWindow extends EventTarget {
  readonly localStorage = new MemoryStorage();

  constructor(private readonly prefersDark: boolean) {
    super();
  }

  matchMedia(_query: string): { matches: boolean } {
    return { matches: this.prefersDark };
  }
}

interface TestEnvironment {
  readonly window: TestWindow;
  readonly classes: Set<string>;
  readonly style: { colorScheme: string };
  readonly document: {
    documentElement: {
      classList: {
        toggle: (className: string, force?: boolean) => void;
      };
      style: { colorScheme: string };
    };
  };
}

function createEnvironment(prefersDark = false): TestEnvironment {
  const classes = new Set<string>();
  const style = { colorScheme: "" };
  const window = new TestWindow(prefersDark);

  return {
    window,
    classes,
    style,
    document: {
      documentElement: {
        classList: {
          toggle(className, force): void {
            if (force) {
              classes.add(className);
              return;
            }

            classes.delete(className);
          },
        },
        style,
      },
    },
  };
}

function dispatchStorageChange(target: EventTarget, key: string | null, newValue: string | null): void {
  const event = new Event("storage");
  Object.defineProperties(event, {
    key: { value: key },
    newValue: { value: newValue },
  });
  target.dispatchEvent(event);
}

async function installEnvironment(prefersDark = false): Promise<TestEnvironment> {
  vi.unstubAllGlobals();
  vi.resetModules();
  await import("vue");

  const environment = createEnvironment(prefersDark);
  vi.stubGlobal("window", environment.window);
  vi.stubGlobal("document", environment.document);
  return environment;
}

describe("shared theme controller", () => {
  let environment: TestEnvironment;

  beforeEach(async () => {
    environment = await installEnvironment();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("initializes one shared readonly ref from persisted storage", async () => {
    environment.window.localStorage.setItem("pd-theme", "dark");
    const { THEME_STORAGE_KEY, initializeTheme, setTheme, useTheme } = await import("./theme");

    const firstInstance = initializeTheme();
    const secondInstance = useTheme();

    expect(THEME_STORAGE_KEY).toBe("pd-theme");
    expect(firstInstance).toBe(secondInstance);
    expect(firstInstance.theme).toBe(secondInstance.theme);
    expect(firstInstance.theme.value).toBe("dark");
    expect(environment.classes.has("dark")).toBe(true);
    expect(environment.style.colorScheme).toBe("dark");

    setTheme("light");
    expect(secondInstance.theme.value).toBe("light");
    expect(environment.window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("uses the system preference when storage is empty and persists explicit toggles", async () => {
    environment = await installEnvironment(true);

    const { THEME_STORAGE_KEY, initializeTheme, toggleTheme } = await import("./theme");
    const state = initializeTheme();

    expect(state.theme.value).toBe("dark");
    toggleTheme();

    expect(state.theme.value).toBe("light");
    expect(environment.classes.has("dark")).toBe(false);
    expect(environment.style.colorScheme).toBe("light");
    expect(environment.window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("synchronizes valid same-origin storage events without writing back", async () => {
    const { THEME_STORAGE_KEY, initializeTheme, useTheme } = await import("./theme");
    const setItem = vi.spyOn(environment.window.localStorage, "setItem");

    initializeTheme();
    setItem.mockClear();
    dispatchStorageChange(environment.window, THEME_STORAGE_KEY, "dark");

    expect(useTheme().theme.value).toBe("dark");
    expect(environment.classes.has("dark")).toBe(true);
    expect(environment.style.colorScheme).toBe("dark");
    expect(setItem).not.toHaveBeenCalled();

    dispatchStorageChange(environment.window, "unrelated-key", "light");
    expect(useTheme().theme.value).toBe("dark");
  });
});
