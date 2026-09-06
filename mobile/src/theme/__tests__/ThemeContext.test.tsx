import { act, renderHook, waitFor } from "@testing-library/react-native";
import React from "react";

import { secureStorage } from "../../lib/secureStorage";
import { ThemeProvider, useTheme } from "../ThemeContext";
import { darkColors, lightColors } from "../tokens";

jest.mock("../../lib/secureStorage", () => {
  const store = new Map<string, string>();
  return {
    secureStorage: {
      getItem: jest.fn((key: string) => Promise.resolve(store.get(key) ?? null)),
      setItem: jest.fn((key: string, value: string) => {
        store.set(key, value);
        return Promise.resolve();
      }),
      removeItem: jest.fn((key: string) => {
        store.delete(key);
        return Promise.resolve();
      }),
      __store: store,
    },
  };
});

const mockStorage = secureStorage as unknown as {
  getItem: jest.Mock;
  setItem: jest.Mock;
  __store: Map<string, string>;
};

const wrapper = ({ children }: { children: React.ReactNode }): React.JSX.Element => (
  <ThemeProvider>{children}</ThemeProvider>
);

describe("ThemeContext", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockStorage.__store.clear();
  });

  it("follows the system scheme by default and becomes ready after reading storage", async () => {
    const { result } = await renderHook(() => useTheme(), { wrapper });

    await waitFor(() => expect(result.current.ready).toBe(true));

    expect(result.current.mode).toBe("system");
    // Jest's react-native environment reports a light (or null) scheme.
    expect(result.current.isDark).toBe(false);
    expect(result.current.colors).toEqual(lightColors);
    expect(mockStorage.getItem).toHaveBeenCalledWith("yatra_theme_mode");
  });

  it("applies a persisted preference on launch", async () => {
    mockStorage.__store.set("yatra_theme_mode", "dark");

    const { result } = await renderHook(() => useTheme(), { wrapper });

    await waitFor(() => expect(result.current.isDark).toBe(true));
    expect(result.current.mode).toBe("dark");
    expect(result.current.colors).toEqual(darkColors);
  });

  it("ignores an invalid persisted value", async () => {
    mockStorage.__store.set("yatra_theme_mode", "neon");

    const { result } = await renderHook(() => useTheme(), { wrapper });

    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.mode).toBe("system");
  });

  it("setMode applies immediately and persists the choice", async () => {
    const { result } = await renderHook(() => useTheme(), { wrapper });
    await waitFor(() => expect(result.current.ready).toBe(true));

    await act(async () => {
      await result.current.setMode("dark");
    });

    expect(result.current.mode).toBe("dark");
    expect(result.current.isDark).toBe(true);
    expect(mockStorage.setItem).toHaveBeenCalledWith("yatra_theme_mode", "dark");

    await act(async () => {
      await result.current.setMode("light");
    });

    expect(result.current.isDark).toBe(false);
    expect(mockStorage.__store.get("yatra_theme_mode")).toBe("light");
  });

  it("works without a provider (isolated component tests, root error fallback)", async () => {
    const { result } = await renderHook(() => useTheme());

    expect(result.current.ready).toBe(true);
    expect(result.current.mode).toBe("system");
    expect(result.current.isDark).toBe(false);
    await expect(result.current.setMode("dark")).resolves.toBeUndefined();
    // No provider means nothing to persist — and nothing should be written.
    expect(mockStorage.setItem).not.toHaveBeenCalled();
  });
});
