import { getRequestConfig } from "next-intl/server";

// The UI ships in Turkish. Adding a language means adding src/messages/<locale>.json and
// choosing the locale here (cookie, header or route segment). Components only use keys.
export const DEFAULT_LOCALE = "tr" as const;

export default getRequestConfig(async () => {
  const locale = DEFAULT_LOCALE;
  return {
    locale,
    timeZone: "Europe/Istanbul",
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
