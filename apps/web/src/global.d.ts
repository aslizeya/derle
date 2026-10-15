import type messages from "./messages/tr.json";

declare module "next-intl" {
  interface AppConfig {
    Locale: "tr";
    Messages: typeof messages;
  }
}
