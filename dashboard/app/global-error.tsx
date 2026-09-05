"use client";

/**
 * Root error boundary. Self-contained on purpose (no layout, no navigation hooks) so Next can prerender it;
 * the root layout's client hooks are not available while built-in error pages are generated.
 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "ui-monospace, monospace", padding: "2rem", maxWidth: 560 }}>
        <h1 style={{ fontSize: 18, fontWeight: 600 }}>focos hit an error</h1>
        <p style={{ fontSize: 13, opacity: 0.8 }}>{error?.message || "Something went wrong while rendering this page."}</p>
        {error?.digest ? <p style={{ fontSize: 11, opacity: 0.6 }}>digest {error.digest}</p> : null}
        <p style={{ fontSize: 13 }}>
          <button type="button" onClick={reset} style={{ padding: "6px 12px", border: "1px solid currentColor", borderRadius: 6, background: "transparent", color: "inherit" }}>
            Try again
          </button>{" "}
          <a href="/health" style={{ marginLeft: 12 }}>Open Health</a>
        </p>
      </body>
    </html>
  );
}
