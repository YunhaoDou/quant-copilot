"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type HealthState =
  | { status: "loading" }
  | { status: "ok"; backend: any; health: any }
  | { status: "error"; error: string };

export default function Home() {
  const [state, setState] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    Promise.all([
      fetch(`${API_URL}/`).then((r) => r.json()),
      fetch(`${API_URL}/health`).then((r) => r.json()),
    ])
      .then(([backend, health]) =>
        setState({ status: "ok", backend, health })
      )
      .catch((e) => setState({ status: "error", error: String(e) }));
  }, []);

  return (
    <main className="max-w-3xl mx-auto p-10">
      <h1 className="text-3xl font-medium">Quant Copilot</h1>
      <p className="text-sm text-gray-500 mt-1">
        AI-powered quant research platform · Phase 0 scaffold
      </p>

      <section className="mt-8">
        <h2 className="text-xl font-medium border-b pb-2">System status</h2>
        {state.status === "loading" && <p className="mt-4">Loading...</p>}
        {state.status === "error" && (
          <p className="mt-4 text-red-600">Backend unreachable: {state.error}</p>
        )}
        {state.status === "ok" && (
          <pre className="mt-4 p-4 bg-gray-50 border rounded text-xs overflow-x-auto">
            {JSON.stringify({ backend: state.backend, health: state.health }, null, 2)}
          </pre>
        )}
      </section>

      <footer className="mt-12 text-xs text-gray-400">
        Backend API base: <code>{API_URL}</code>
      </footer>
    </main>
  );
}
