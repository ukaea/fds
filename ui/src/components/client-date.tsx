"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

export function ClientDate({ timestamp }: { timestamp?: string | number | Date }) {
  // Formatted in the reader's locale, so the server cannot render it: it would
  // send one locale's text and the client would replace it with another's.
  const dateString = useSyncExternalStore(
    subscribe,
    () => (timestamp ? new Date(timestamp).toLocaleString() : ""),
    () => "",
  );

  if (!dateString) return null;

  return <span>{dateString}</span>;
}
