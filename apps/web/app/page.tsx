"use client";

import { useEffect, useState } from "react";

type ApiState =
  | { kind: "checking"; detail: string }
  | { kind: "online"; detail: string }
  | { kind: "offline"; detail: string };

const API_URL = process.env.NEXT_PUBLIC_STK_API_URL ?? "http://127.0.0.1:8000";

async function probeApi(): Promise<ApiState> {
  try {
    const response = await fetch(`${API_URL}/health/live`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = (await response.json()) as { version: string };
    return { kind: "online", detail: `API v${data.version} disponível` };
  } catch {
    return { kind: "offline", detail: "API indisponível neste endereço" };
  }
}

export default function Home() {
  const [api, setApi] = useState<ApiState>({
    kind: "checking",
    detail: "Verificando a fundação local…"
  });

  async function checkApi() {
    setApi({ kind: "checking", detail: "Verificando a fundação local…" });
    setApi(await probeApi());
  }

  useEffect(() => {
    let active = true;
    void probeApi().then((result) => {
      if (active) setApi(result);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main>
      <section className="hero">
        <div className="eyebrow">GRUPO STK · FUNDAÇÃO V1</div>
        <h1>Uma base operacional confiável antes da automação.</h1>
        <p className="intro">
          As Etapas 0 e 1 estabelecem identidade, estrutura jurídica e trilha de controle. O
          backend permanece dono das regras, transações e autorização.
        </p>
        <div className={`health health-${api.kind}`} role="status" aria-live="polite">
          <span className="health-dot" aria-hidden="true" />
          <span>{api.detail}</span>
          <button type="button" onClick={() => void checkApi()}>
            Verificar novamente
          </button>
        </div>
      </section>

      <section className="foundation" aria-label="Fundação implementada">
        <article>
          <span>01</span>
          <h2>Domínio sem ambiguidade</h2>
          <p>Grupo, entidade jurídica, estabelecimento fiscal e unidade de negócio.</p>
        </article>
        <article>
          <span>02</span>
          <h2>Acesso controlado</h2>
          <p>Administrador e contas de serviço autorizados por capacidades explícitas.</p>
        </article>
        <article>
          <span>03</span>
          <h2>Rastro transacional</h2>
          <p>Correlação, idempotência, auditoria append-only, inbox, outbox e exceções.</p>
        </article>
      </section>

      <footer>
        <span>STK OS</span>
        <span>Etapa 2 não iniciada</span>
      </footer>
    </main>
  );
}
