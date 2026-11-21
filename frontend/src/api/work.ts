import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { HubBridgeChat, HubBridgeContact, HubBridgeDeal } from "./commerce";

export type ProjectStatus = "planning" | "active" | "review" | "done" | "paused";
export type TaskStatus = "todo" | "doing" | "done";
export type TaskPriority = "low" | "medium" | "high" | "urgent";

export interface ChecklistItem {
  id: string;
  text: string;
  done: boolean;
}

export interface WorkProject {
  id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  contact_id: string | null;
  contact_name: string | null;
  crm_deal_id: string | null;
  proposal_id: string | null;
  budget_project_id: string | null;
  budget_value: string;
  hourly_rate: string;
  start_date: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
  total_hours: string;
  expenses_total: string;
  net_margin: string;
  effective_hourly_rate: string;
  tasks_todo: number;
  tasks_doing: number;
  tasks_done: number;
  tasks_total: number;
}

export interface ProjectTask {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  checklist: ChecklistItem[];
  position: number;
  source_chat_id: string | null;
  source_message_id: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectTimeEntry {
  id: string;
  project_id: string;
  task_id: string | null;
  task_title: string | null;
  hours: string;
  entry_date: string;
  notes: string | null;
  created_at: string;
}

export interface ProjectDetailResponse {
  project: WorkProject;
  tasks: ProjectTask[];
  time_entries: ProjectTimeEntry[];
}

export type AgendaEventKind = "meeting" | "delivery" | "visit" | "reminder" | "personal";
export type AgendaEventStatus = "scheduled" | "confirmed" | "done" | "cancelled";
export type AgendaLayer = "agenda" | "messaging" | "crm" | "projects" | "budget" | "cofre";

export interface AgendaTimelineItem {
  uid: string;
  id: string;
  layer: AgendaLayer;
  kind: string;
  title: string;
  subtitle: string | null;
  date: string;
  time: string | null;
  status: string;
  location?: string | null;
  contact_id?: string | null;
  project_id?: string | null;
  project_name?: string | null;
  messaging_chat_id?: string | null;
  chat_name?: string | null;
  notes?: string | null;
}

export interface AgendaTimelineResponse {
  start_date: string;
  end_date: string;
  items: AgendaTimelineItem[];
  counts_by_layer: Record<AgendaLayer, number>;
}

export interface ProjectBridges {
  contacts: HubBridgeContact[];
  deals: HubBridgeDeal[];
  proposals: {
    id: string;
    title: string;
    number: number;
    total_amount: string;
    customer_name: string;
  }[];
  budget_tags: { id: string; name: string; budget: string }[];
}

export interface AgendaBridges {
  contacts: HubBridgeContact[];
  chats: HubBridgeChat[];
  projects: { id: string; name: string; status: ProjectStatus }[];
}

export const projectsKeys = {
  list: (status = "all") => ["projects", "list", status] as const,
  detail: (id: string) => ["projects", "detail", id] as const,
  bridges: ["projects", "bridges"] as const,
};

export const agendaKeys = {
  timeline: (start: string, end: string, layersKey: string) =>
    ["agenda", "timeline", start, end, layersKey] as const,
  bridges: ["agenda", "bridges"] as const,
};

export const projectsApi = {
  list: (status?: ProjectStatus | "") => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return api.get<WorkProject[]>(`/work/projects${qs}`);
  },
  detail: (id: string) => api.get<ProjectDetailResponse>(`/work/projects/${id}`),
  create: (body: {
    name: string;
    description?: string;
    status: ProjectStatus;
    contact_id?: string | null;
    crm_deal_id?: string | null;
    proposal_id?: string | null;
    budget_project_id?: string | null;
    budget_value: number;
    hourly_rate: number;
    start_date?: string | null;
    due_date?: string | null;
    link_budget_tag?: boolean;
  }) => api.post<WorkProject>("/work/projects", body),
  update: (id: string, body: Partial<WorkProject>) =>
    api.patch<WorkProject>(`/work/projects/${id}`, body),
  delete: (id: string) => api.delete(`/work/projects/${id}`),
  createTask: (
    projectId: string,
    body: {
      title: string;
      description?: string;
      status?: TaskStatus;
      priority: TaskPriority;
      due_date?: string | null;
      checklist?: { text: string; done: boolean }[];
    },
  ) => api.post<ProjectTask>(`/work/projects/${projectId}/tasks`, body),
  updateTask: (
    taskId: string,
    body: {
      title?: string;
      description?: string | null;
      status?: TaskStatus;
      priority?: TaskPriority;
      due_date?: string | null;
      checklist?: ChecklistItem[];
    },
  ) => api.patch<ProjectTask>(`/work/projects/tasks/${taskId}`, body),
  deleteTask: (taskId: string) => api.delete(`/work/projects/tasks/${taskId}`),
  addTimeEntry: (
    projectId: string,
    body: { task_id?: string | null; hours: number; entry_date: string; notes?: string },
  ) => api.post<ProjectTimeEntry>(`/work/projects/${projectId}/time-entries`, body),
  deleteTimeEntry: (entryId: string) => api.delete(`/work/projects/time-entries/${entryId}`),
  bridges: () => api.get<ProjectBridges>("/work/projects/hub/bridges"),
};

export const agendaApi = {
  timeline: (start: string, end: string, layers?: AgendaLayer[]) => {
    const sp = new URLSearchParams({ start, end });
    if (layers && layers.length > 0) sp.set("layers", layers.join(","));
    return api.get<AgendaTimelineResponse>(`/agenda/timeline?${sp.toString()}`);
  },
  createEvent: (body: {
    title: string;
    kind: AgendaEventKind;
    start_at: string;
    end_at?: string | null;
    all_day?: boolean;
    location?: string;
    status?: AgendaEventStatus;
    contact_id?: string | null;
    project_id?: string | null;
    messaging_chat_id?: string | null;
    notes?: string;
  }) => api.post<Record<string, unknown>>("/agenda/events", body),
  updateEvent: (
    eventId: string,
    body: Partial<{
      title: string;
      kind: AgendaEventKind;
      start_at: string;
      all_day: boolean;
      location: string | null;
      status: AgendaEventStatus;
      contact_id: string | null;
      project_id: string | null;
      messaging_chat_id: string | null;
      notes: string | null;
    }>,
  ) => api.patch<Record<string, unknown>>(`/agenda/events/${eventId}`, body),
  deleteEvent: (eventId: string) => api.delete(`/agenda/events/${eventId}`),
  confirmWhatsapp: (
    eventId: string,
    body: { send_now: boolean; custom_text?: string },
  ) =>
    api.post<{
      event_id: string;
      chat_id: string | null;
      chat_name: string | null;
      text: string;
      sent: boolean;
    }>(`/agenda/events/${eventId}/confirm-whatsapp`, body),
  bridges: () => api.get<AgendaBridges>("/agenda/hub/bridges"),
};

export function useProjects(status: ProjectStatus | "" = "") {
  return useQuery({
    queryKey: projectsKeys.list(status || "all"),
    queryFn: () => projectsApi.list(status),
  });
}

export function useProjectDetail(projectId: string | null) {
  return useQuery({
    queryKey: projectsKeys.detail(projectId ?? "none"),
    queryFn: () => projectsApi.detail(projectId!),
    enabled: Boolean(projectId),
  });
}

export function useProjectsBridges(enabled = true) {
  return useQuery({
    queryKey: projectsKeys.bridges,
    queryFn: projectsApi.bridges,
    enabled,
  });
}

export function useAgendaTimeline(start: string, end: string, layers: AgendaLayer[]) {
  const layersKey = layers.slice().sort().join(",");
  return useQuery({
    queryKey: agendaKeys.timeline(start, end, layersKey),
    queryFn: () => agendaApi.timeline(start, end, layers),
  });
}

export function useAgendaBridges(enabled = true) {
  return useQuery({
    queryKey: agendaKeys.bridges,
    queryFn: agendaApi.bridges,
    enabled,
  });
}
