"use client";

import { useEffect, useState } from "react";

type Task = { id: string; business_unit_id: string; title: string; due_at: string; priority: string; status: string };
type Unit = { id: string; name: string };

export default function TasksWorkspace({ apiUrl, token, units, activeUnitId, onNotice }: { apiUrl: string; token: string; units: Unit[]; activeUnitId: string; onNotice: (kind: "success" | "error", text: string) => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<"all" | "overdue" | "today" | "next">("all");
  async function load() {
    const query = activeUnitId ? `?business_unit_id=${activeUnitId}` : "";
    const response = await fetch(`${apiUrl}/api/v1/crm/tasks${query}`, { cache: "no-store", headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new Error("Falha ao carregar tarefas");
    setTasks(await response.json() as Task[]);
  }
  useEffect(() => {
    let cancelled = false;
    const query = activeUnitId ? `?business_unit_id=${activeUnitId}` : "";
    void fetch(`${apiUrl}/api/v1/crm/tasks${query}`, { cache: "no-store", headers: { Authorization: `Bearer ${token}` } })
      .then((response) => { if (!response.ok) throw new Error("Falha ao carregar tarefas"); return response.json() as Promise<Task[]>; })
      .then((items) => { if (!cancelled) setTasks(items); })
      .catch((error) => onNotice("error", error instanceof Error ? error.message : "Falha nas tarefas"));
    return () => { cancelled = true; };
  }, [activeUnitId, apiUrl, token, onNotice]);
  async function complete(id: string) {
    const response = await fetch(`${apiUrl}/api/v1/crm/tasks/${id}/complete`, { method: "PATCH", headers: { Authorization: `Bearer ${token}`, "Idempotency-Key": crypto.randomUUID() } });
    if (!response.ok) return onNotice("error", "Falha ao concluir tarefa");
    await load(); onNotice("success", "Tarefa concluída.");
  }
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today); tomorrow.setDate(tomorrow.getDate() + 1);
  const visible = tasks.filter((task) => { const due = new Date(task.due_at); if (filter === "overdue") return task.status === "open" && due < today; if (filter === "today") return due >= today && due < tomorrow; if (filter === "next") return due >= tomorrow; return true; });
  return <section className="workspace tasks-workspace"><header className="contracts-header"><div><p className="overline">EXECUÇÃO OPERACIONAL</p><h1>Tarefas</h1><p>Ações reais do CRM organizadas por prazo e contexto de unidade.</p></div></header><div className="task-layout-real"><aside className="task-filters-real">{(["all", "today", "overdue", "next"] as const).map((item) => <button className={filter === item ? "active" : ""} type="button" key={item} onClick={() => setFilter(item)}>{item === "all" ? "Todas" : item === "today" ? "Hoje" : item === "overdue" ? "Atrasadas" : "Próximas"}</button>)}</aside><section className="task-list-real">{visible.map((task) => <article key={task.id}><button aria-label="Concluir tarefa" disabled={task.status !== "open"} type="button" onClick={() => void complete(task.id)}>{task.status === "completed" ? "✓" : "○"}</button><div><strong>{task.title}</strong><span>{units.find((unit) => unit.id === task.business_unit_id)?.name ?? "Unidade"}</span></div><time>{new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(task.due_at))}</time><span className={`state-pill ${task.status === "completed" ? "active" : "scheduled"}`}>{task.status}</span></article>)}{!visible.length && <p className="muted">Nenhuma tarefa neste recorte.</p>}</section></div></section>;
}
