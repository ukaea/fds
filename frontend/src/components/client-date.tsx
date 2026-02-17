"use client";

import { useEffect, useState } from "react";

export function ClientDate({ timestamp }: { timestamp?: string | number | Date }) {
  const [dateString, setDateString] = useState<string>("");

  useEffect(() => {
    if (timestamp) {
      setDateString(new Date(timestamp).toLocaleString());
    }
  }, [timestamp]);

  if (!dateString) return null;

  return <span>{dateString}</span>;
}
