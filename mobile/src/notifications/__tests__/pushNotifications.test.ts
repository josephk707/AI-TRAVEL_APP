import type * as NotificationsModule from "expo-notifications";

jest.mock("../../api/notifications", () => ({
  registerPushToken: jest.fn(),
  unregisterPushToken: jest.fn(),
}));

jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
}));

// `registeredToken` in pushNotifications.ts is deliberate module-level
// state (there is exactly one device push token per app instance) — reset
// the module registry before each test so that state doesn't leak between
// otherwise-independent test cases in this file.
function loadModules() {
  jest.resetModules();
  const notificationsApi = jest.requireMock("../../api/notifications") as {
    registerPushToken: jest.Mock;
    unregisterPushToken: jest.Mock;
  };
  const expoNotifications = jest.requireMock(
    "expo-notifications",
  ) as unknown as jest.Mocked<typeof NotificationsModule>;
  const pushNotifications = jest.requireActual("../pushNotifications") as typeof import("../pushNotifications");
  return { notificationsApi, expoNotifications, pushNotifications };
}

describe("registerForPushNotifications", () => {
  it("registers the real Expo push token with the backend once permission is granted", async () => {
    const { notificationsApi, expoNotifications, pushNotifications } = loadModules();
    (expoNotifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
    (expoNotifications.getExpoPushTokenAsync as jest.Mock).mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });

    await pushNotifications.registerForPushNotifications();

    expect(notificationsApi.registerPushToken).toHaveBeenCalledWith(
      "ExponentPushToken[abc123]",
      expect.stringMatching(/ios|android/),
    );
  });

  it("requests permission when not already granted, and registers on success", async () => {
    const { notificationsApi, expoNotifications, pushNotifications } = loadModules();
    (expoNotifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "undetermined" });
    (expoNotifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
    (expoNotifications.getExpoPushTokenAsync as jest.Mock).mockResolvedValue({
      data: "ExponentPushToken[xyz789]",
    });

    await pushNotifications.registerForPushNotifications();

    expect(expoNotifications.requestPermissionsAsync).toHaveBeenCalled();
    expect(notificationsApi.registerPushToken).toHaveBeenCalledWith(
      "ExponentPushToken[xyz789]",
      expect.any(String),
    );
  });

  it("never registers a token, and never throws, when permission is denied", async () => {
    const { notificationsApi, expoNotifications, pushNotifications } = loadModules();
    (expoNotifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "undetermined" });
    (expoNotifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied" });

    await expect(pushNotifications.registerForPushNotifications()).resolves.toBeUndefined();
    expect(notificationsApi.registerPushToken).not.toHaveBeenCalled();
  });

  it("swallows a token-fetch failure (e.g. simulator, missing config) without throwing", async () => {
    const { notificationsApi, expoNotifications, pushNotifications } = loadModules();
    (expoNotifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
    (expoNotifications.getExpoPushTokenAsync as jest.Mock).mockRejectedValue(
      new Error("no push capability in this environment"),
    );

    await expect(pushNotifications.registerForPushNotifications()).resolves.toBeUndefined();
    expect(notificationsApi.registerPushToken).not.toHaveBeenCalled();
  });
});

describe("unregisterCurrentPushToken", () => {
  it("is a no-op when no token was ever registered", async () => {
    const { notificationsApi, pushNotifications } = loadModules();

    await expect(pushNotifications.unregisterCurrentPushToken()).resolves.toBeUndefined();
    expect(notificationsApi.unregisterPushToken).not.toHaveBeenCalled();
  });

  it("unregisters the previously registered token", async () => {
    const { notificationsApi, expoNotifications, pushNotifications } = loadModules();
    (expoNotifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
    (expoNotifications.getExpoPushTokenAsync as jest.Mock).mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });
    await pushNotifications.registerForPushNotifications();

    await pushNotifications.unregisterCurrentPushToken();

    expect(notificationsApi.unregisterPushToken).toHaveBeenCalledWith("ExponentPushToken[abc123]");
  });

  it("never throws even when the unregister call itself fails", async () => {
    const { notificationsApi, expoNotifications, pushNotifications } = loadModules();
    (expoNotifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted" });
    (expoNotifications.getExpoPushTokenAsync as jest.Mock).mockResolvedValue({
      data: "ExponentPushToken[abc123]",
    });
    await pushNotifications.registerForPushNotifications();
    notificationsApi.unregisterPushToken.mockRejectedValue(new Error("network error"));

    await expect(pushNotifications.unregisterCurrentPushToken()).resolves.toBeUndefined();
  });
});
