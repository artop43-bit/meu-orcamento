import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ArchiveRestore,
  Briefcase,
  CalendarClock,
  LayoutDashboard,
  Pin,
  PinOff,
  Plus,
  Send,
  Tag,
  Trash2,
  Wallet,
  X,
} from "lucide-react";

import { errorMessage } from "../../api/client";
import { crmApi, crmKeys } from "../../api/crm";
import {
  messagingApi,
  messagingKeys,
  useBudgetContext,
  useChatCrmContext,
  type MessagingChat,
} from "../../api/messaging";
import { announce } from "../../lib/announce";
import { money, parseMoney } from "../../lib/format";
import {
  chatPhoneLabel,
  expandQuickReply,
  hasVisiblePhone,
  PRESET_CHAT_TAGS,
  SERVICE_STATUS_LABELS,
  type ServiceStatus,
} from "../../lib/messaging";
import { Sheet } from "../ui";

type ChatChanges = Parameters<typeof messagingApi.updateChat>[1];

function toDatetimeLocalValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * Janela "Dados do contato & CRM 360°": nome, etiquetas, status de atendimento, follow-up,
 * negócios no Funil do Dashboard & CRM, saldo e cobrança Pix no Meu Orçamento.
 */
export function ContactSheet({
  open,
  chat,
  onClose,
  onDeleted,
  onFillDraft,
}: {
  open: boolean;
  chat: MessagingChat | null;
  onClose: () => void;
  onDeleted: () => void;
  onFillDraft?: (text: string) => void;
}) {
  const queryClient = useQueryClient();
  const [editName, setEditName] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editBudgetPerson, setEditBudgetPerson] = useState("");
  const [editTags, setEditTags] = useState<string[]>([]);
  const [customTag, setCustomTag] = useState("");
  const [editStatus, setEditStatus] = useState<ServiceStatus>("open");
  const [editFollowupAt, setEditFollowupAt] = useState("");
  const [editFollowupNote, setEditFollowupNote] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crmSavedMsg, setCrmSavedMsg] = useState<string | null>(null);

  const [newDealOpen, setNewDealOpen] = useState(false);
  const [dealTitle, setDealTitle] = useState("");
  const [dealValue, setDealValue] = useState("");
  const [dealStageId, setDealStageId] = useState("");

  const budgetCtx = useBudgetContext(chat?.id ?? null, open && Boolean(chat));
  const crmCtx = useChatCrmContext(chat?.id ?? null, open && Boolean(chat));

  // Ao abrir, os campos começam com os dados atuais do contato.
  useEffect(() => {
    if (!open || !chat) return;
    setEditName(chat.name);
    setEditNotes(chat.notes ?? "");
    setEditBudgetPerson(chat.budget_person ?? "");
    setEditTags(chat.tags ?? []);
    setCustomTag("");
    setEditStatus(chat.service_status ?? "open");
    setEditFollowupAt(toDatetimeLocalValue(chat.followup_at));
    setEditFollowupNote(chat.followup_note ?? "");
    setConfirmDelete(false);
    setError(null);
    setCrmSavedMsg(null);
    setNewDealOpen(false);
    setDealTitle("");
    setDealValue("");
    setDealStageId("");
  }, [open, chat?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const sendToCrm = useMutation({
    mutationFn: (id: string) => crmApi.importFromMessaging(id),
    onSuccess: (res) => {
      setError(null);
      setCrmSavedMsg(
        res.created ? "Contato salvo no Dashboard & CRM." : "Contato já estava vinculado no Dashboard & CRM.",
      );
      void queryClient.invalidateQueries({ queryKey: ["crm", "contacts"] });
      void queryClient.invalidateQueries({ queryKey: crmKeys.sources });
      if (chat) void queryClient.invalidateQueries({ queryKey: messagingKeys.crmContext(chat.id) });
      announce("Contato enviado para o Dashboard & CRM.");
    },
    onError: (err) => setError(errorMessage(err)),
  });

  const createDealMutation = useMutation({
    mutationFn: () =>
      messagingApi.createCrmDeal(chat!.id, {
        title: dealTitle.trim(),
        value: parseMoney(dealValue || "0") ?? "",
        stage_id: dealStageId || null,
      }),
    onSuccess: () => {
      setDealTitle("");
      setDealValue("");
      setNewDealOpen(false);
      setCrmSavedMsg("Negócio criado no Funil do Dashboard & CRM.");
      if (chat) void queryClient.invalidateQueries({ queryKey: messagingKeys.crmContext(chat.id) });
      void queryClient.invalidateQueries({ queryKey: crmKeys.pipeline });
      announce("Negócio criado no Funil CRM.");
    },
    onError: (err) => setError(errorMessage(err)),
  });

  const changeDealStageMutation = useMutation({
    mutationFn: ({ dealId, stageId }: { dealId: string; stageId: string }) =>
      crmApi.updateDeal(dealId, { stage_id: stageId }),
    onSuccess: () => {
      if (chat) void queryClient.invalidateQueries({ queryKey: messagingKeys.crmContext(chat.id) });
      void queryClient.invalidateQueries({ queryKey: crmKeys.pipeline });
    },
    onError: (err) => setError(errorMessage(err)),
  });

  const updateChat = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ChatChanges }) => messagingApi.updateChat(id, data),
    onSuccess: (updated) => {
      setError(null);
      queryClient.setQueryData(messagingKeys.chat(updated.id), updated);
      void queryClient.invalidateQueries({ queryKey: messagingKeys.chatLists });
      void queryClient.invalidateQueries({ queryKey: messagingKeys.budgetContext(updated.id) });
      announce("Contato atualizado.");
    },
    onError: (err) => setError(errorMessage(err)),
  });

  const deleteChat = useMutation({
    mutationFn: (id: string) => messagingApi.deleteChat(id),
    onSuccess: (_, id) => {
      setConfirmDelete(false);
      queryClient.removeQueries({ queryKey: messagingKeys.chat(id) });
      queryClient.removeQueries({ queryKey: messagingKeys.messages(id) });
      void queryClient.invalidateQueries({ queryKey: messagingKeys.chatLists });
      void queryClient.invalidateQueries({ queryKey: messagingKeys.session });
      announce("Conversa excluída.");
      onDeleted();
    },
    onError: (err) => setError(errorMessage(err)),
  });

  function toggleTag(tag: string) {
    setEditTags((prev) => {
      const exists = prev.some((t) => t.toLowerCase() === tag.toLowerCase());
      if (exists) return prev.filter((t) => t.toLowerCase() !== tag.toLowerCase());
      return [...prev, tag].slice(0, 8);
    });
  }

  function addCustomTag() {
    const clean = customTag.trim().replace(/,/g, "");
    if (!clean) return;
    if (!editTags.some((t) => t.toLowerCase() === clean.toLowerCase())) {
      setEditTags((prev) => [...prev, clean].slice(0, 8));
    }
    setCustomTag("");
  }

  function applyFollowupPreset(hoursFromNow: number | "tomorrow9" | "clear") {
    if (hoursFromNow === "clear") {
      setEditFollowupAt("");
      setEditFollowupNote("");
      return;
    }
    const target = new Date();
    if (hoursFromNow === "tomorrow9") {
      target.setDate(target.getDate() + 1);
      target.setHours(9, 0, 0, 0);
    } else {
      target.setTime(target.getTime() + hoursFromNow * 3_600_000);
    }
    setEditFollowupAt(toDatetimeLocalValue(target.toISOString()));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!chat) return;
    const followupIso = editFollowupAt ? new Date(editFollowupAt).toISOString() : null;
    updateChat.mutate(
      {
        id: chat.id,
        data: {
          name: editName.trim(),
          notes: editNotes.trim() || null,
          budget_person: editBudgetPerson || null,
          tags: editTags,
          service_status: editStatus,
          followup_at: followupIso,
          followup_note: editFollowupNote.trim() || null,
        },
      },
      { onSuccess: onClose },
    );
  }

  function handleSendPixInChat() {
    if (!chat || !onFillDraft) return;
    const owesMe = linked ? Number(linked.owes_me) : 0;
    const template =
      owesMe > 0
        ? "Oi {nome}, tudo bem? Passando para lembrar do valor pendente de {valor_pendente}. Minha chave Pix é: {chave_pix}"
        : "Oi {nome}! Segue minha chave Pix para pagamento: {chave_pix}";
    const msg = expandQuickReply(template, {
      nome: chat.name,
      telefone: chat.phone_display,
      chave_pix: budgetCtx.data?.pix_key,
      valor_pendente: owesMe > 0 ? money(owesMe) : "R$ 0,00",
    });
    onFillDraft(msg);
    onClose();
  }

  const linked = budgetCtx.data?.linked_contact ?? null;
  const net = linked ? Number(linked.net) : 0;
  const crmDeals = crmCtx.data?.deals ?? [];
  const crmStages = crmCtx.data?.stages ?? [];

  return (
    <Sheet
      open={open && Boolean(chat)}
      title="Dados do contato & CRM 360°"
      onClose={() => {
        setConfirmDelete(false);
        onClose();
      }}
    >
      {chat && (
        <div className="stack">
          <form className="inline-form stack" onSubmit={submit}>
            {error && (
              <p className="alert alert--error m-0" role="alert">
                {error}
              </p>
            )}
            <div className="wa-contact-meta">
              <span className="muted small">WhatsApp</span>
              <strong className={hasVisiblePhone(chat) ? undefined : "muted"}>{chatPhoneLabel(chat)}</strong>
            </div>

            <label className="field">
              <span className="field-label">Nome</span>
              <input type="text" required value={editName} onChange={(event) => setEditName(event.target.value)} />
            </label>

            <div className="field">
              <span className="field-label">Status do atendimento</span>
              <div className="wa-filters" role="group" aria-label="Status do atendimento">
                {(["open", "waiting", "resolved"] as const).map((st) => (
                  <button
                    key={st}
                    type="button"
                    className={`filter-chip ${editStatus === st ? "is-active" : ""}`}
                    aria-pressed={editStatus === st}
                    onClick={() => setEditStatus(st)}
                  >
                    {SERVICE_STATUS_LABELS[st]}
                  </button>
                ))}
              </div>
            </div>

            <div className="field">
              <span className="field-label">Etiquetas da conversa</span>
              <div className="wa-tag-filters">
                {Array.from(new Set([...PRESET_CHAT_TAGS, ...editTags])).map((tag) => {
                  const active = editTags.some((t) => t.toLowerCase() === tag.toLowerCase());
                  return (
                    <button
                      key={tag}
                      type="button"
                      className={`wa-tag-chip ${active ? "is-active" : ""}`}
                      aria-pressed={active}
                      onClick={() => toggleTag(tag)}
                    >
                      <Tag size={10} aria-hidden />
                      {tag}
                    </button>
                  );
                })}
              </div>
              <div className="row row--tight mt-2">
                <input
                  type="text"
                  placeholder="Nova etiqueta..."
                  aria-label="Nova etiqueta"
                  value={customTag}
                  maxLength={32}
                  onChange={(e) => setCustomTag(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addCustomTag();
                    }
                  }}
                />
                <button type="button" className="btn btn--secondary btn--sm" onClick={addCustomTag}>
                  Adicionar
                </button>
              </div>
            </div>

            <div className="field">
              <span className="field-label">
                <CalendarClock size={13} aria-hidden className="wa-icon-inline" />
                Follow-up agendado (lembrete de retorno)
              </span>
              <div className="row row--tight mb-2">
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={() => applyFollowupPreset(2)}
                >
                  Hoje +2h
                </button>
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={() => applyFollowupPreset("tomorrow9")}
                >
                  Amanhã 09h
                </button>
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={() => applyFollowupPreset(24 * 7)}
                >
                  Em 7 dias
                </button>
                {editFollowupAt && (
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => applyFollowupPreset("clear")}
                  >
                    <X size={13} aria-hidden />
                    Limpar
                  </button>
                )}
              </div>
              <input
                type="datetime-local"
                aria-label="Data e hora do retorno"
                value={editFollowupAt}
                onChange={(e) => setEditFollowupAt(e.target.value)}
              />
              <input
                type="text"
                placeholder="Motivo do retorno (ex.: Cobrar aprovação da proposta)"
                aria-label="Motivo do retorno"
                value={editFollowupNote}
                maxLength={200}
                onChange={(e) => setEditFollowupNote(e.target.value)}
                className="mt-2"
              />
            </div>

            <div className="field">
              <label htmlFor="wa-contact-notes" className="field-label">Observações</label>
              <textarea id="wa-contact-notes" rows={2} value={editNotes} onChange={(event) => setEditNotes(event.target.value)} />
            </div>

            {budgetCtx.data && (
              <label className="field">
                <span className="field-label">Pessoa no Meu Orçamento</span>
                <select value={editBudgetPerson} onChange={(event) => setEditBudgetPerson(event.target.value)}>
                  <option value="">Sem vínculo</option>
                  {budgetCtx.data.contacts.map((contact) => (
                    <option key={contact.person} value={contact.person}>
                      {contact.person}
                    </option>
                  ))}
                  {editBudgetPerson && !budgetCtx.data.contacts.some((c) => c.person === editBudgetPerson) && (
                    <option value={editBudgetPerson}>{editBudgetPerson}</option>
                  )}
                </select>
              </label>
            )}

            <div className="row row--right">
              <button type="submit" className="btn btn--primary" disabled={updateChat.isPending}>
                {updateChat.isPending ? "Salvando…" : "Salvar"}
              </button>
            </div>
          </form>

          {/* Painel 360° — Funil do Dashboard & CRM */}
          <div className="wa-budget-card">
            <div className="row row--between">
              <span className="row row--tight">
                <Briefcase size={16} aria-hidden />
                <strong>Funil Dashboard & CRM</strong>
              </span>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={() => {
                  setNewDealOpen((v) => !v);
                  if (!dealTitle) setDealTitle(`Proposta · ${chat.name}`);
                }}
              >
                <Plus size={13} aria-hidden />
                {newDealOpen ? "Cancelar" : "Novo negócio"}
              </button>
            </div>

            {newDealOpen && (
              <div className="stack mt-3">
                <input
                  type="text"
                  className="input"
                  placeholder="Título do negócio"
                  aria-label="Título do negócio"
                  value={dealTitle}
                  onChange={(e) => setDealTitle(e.target.value)}
                />
                <div className="row row--tight">
                  <input
                    type="text"
                    inputMode="decimal"
                    className="input"
                    placeholder="Valor (R$)"
                    aria-label="Valor do negócio (R$)"
                    value={dealValue}
                    onChange={(e) => setDealValue(e.target.value)}
                  />
                  <select
                    aria-label="Etapa do novo negócio"
                    className="input"
                    value={dealStageId}
                    onChange={(e) => setDealStageId(e.target.value)}
                  >
                    <option value="">Primeira etapa</option>
                    {crmStages.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  disabled={!dealTitle.trim() || createDealMutation.isPending}
                  onClick={() => createDealMutation.mutate()}
                >
                  {createDealMutation.isPending ? "Criando…" : "Criar no Funil CRM"}
                </button>
              </div>
            )}

            {crmDeals.length === 0 ? (
              <p className="muted small mt-1">
                Nenhum negócio vinculado a este contato ainda.
              </p>
            ) : (
              <div className="stack stack--compact mt-2">
                {crmDeals.map((d) => (
                  <div key={d.id} className="wa-crm-deal-row">
                    <div>
                      <strong className="small">{d.title}</strong>
                      <div className="muted small">{money(d.value)}</div>
                    </div>
                    <select
                      className="input wa-crm-stage-select"
                      value={d.stage_id}
                      aria-label={`Etapa de ${d.title}`}
                      onChange={(e) =>
                        changeDealStageMutation.mutate({ dealId: d.id, stageId: e.target.value })
                      }
                    >
                      {crmStages.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Painel 360° — Meu Orçamento & Pix */}
          <div className="wa-budget-card">
            <div className="row row--between">
              <span className="row row--tight">
                <Wallet size={16} aria-hidden />
                <strong>Meu Orçamento</strong>
              </span>
              {onFillDraft && (
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={handleSendPixInChat}
                >
                  <Send size={13} aria-hidden />
                  Cobrar com Pix no chat
                </button>
              )}
            </div>
            {linked ? (
              <p className="small m-0">
                {net > 0
                  ? `${linked.person} te deve ${money(linked.net)}`
                  : net < 0
                    ? `Você deve ${money(Math.abs(net))} para ${linked.person}`
                    : `Sem pendências em aberto com ${linked.person}`}
              </p>
            ) : (
              <p className="muted small m-0">
                Use o botão <strong>Lançar</strong> na conversa ou em qualquer mensagem para registrar receitas e despesas no mês atual.
              </p>
            )}
          </div>

          {crmSavedMsg && (
            <p className="alert alert--success m-0" role="status">
              {crmSavedMsg}
            </p>
          )}

          <div className="wa-contact-actions">
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              disabled={sendToCrm.isPending}
              onClick={() => sendToCrm.mutate(chat.id)}
            >
              <LayoutDashboard size={15} aria-hidden />
              {sendToCrm.isPending ? "Enviando…" : "Salvar no CRM"}
            </button>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => updateChat.mutate({ id: chat.id, data: { pinned: !chat.pinned } })}
            >
              {chat.pinned ? <PinOff size={15} aria-hidden /> : <Pin size={15} aria-hidden />}
              {chat.pinned ? "Desafixar" : "Fixar"}
            </button>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => updateChat.mutate({ id: chat.id, data: { archived: !chat.archived } })}
            >
              {chat.archived ? <ArchiveRestore size={15} aria-hidden /> : <Archive size={15} aria-hidden />}
              {chat.archived ? "Desarquivar" : "Arquivar"}
            </button>
            {!confirmDelete ? (
              <button type="button" className="btn btn--danger btn--sm" onClick={() => setConfirmDelete(true)}>
                <Trash2 size={15} aria-hidden />
                Excluir
              </button>
            ) : (
              <button
                type="button"
                className="btn btn--danger btn--sm"
                onClick={() => deleteChat.mutate(chat.id)}
                disabled={deleteChat.isPending}
              >
                Confirmar exclusão
              </button>
            )}
          </div>
        </div>
      )}
    </Sheet>
  );
}
