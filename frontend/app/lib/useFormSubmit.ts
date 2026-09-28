"use client";

import { useState, type FormEvent } from "react";

/**
 * Runs `handler` on submit and tracks pending/error state. The handler returns an error
 * message, or null on success. Typed values stay in the form when there's an error.
 */
export function useFormSubmit(handler: (form: FormData) => Promise<string | null>) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    const message = await handler(new FormData(event.currentTarget));
    setError(message);
    // On success the page navigates away, so keep the button disabled until it does.
    if (message) setPending(false);
  }

  return { error, pending, onSubmit };
}
