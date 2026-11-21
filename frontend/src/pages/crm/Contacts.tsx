import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, MessageCircle, Plus, Search, Trash2, UserRound, Wallet } from "lucide-react";

import { errorMessage } from "../../api/client";
import {
  crmApi,
  crmKeys,
  useContacts,
  useHubMessagingChats,
  type CrmContact,
} from "../../api/crm";
import { Alert, PageHeader, Sheet } from "../../components/ui";
import { EmptyGuide } from "../../components/help";
import { announce } from "../../lib/announce";

export default function Contacts() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const contactsQuery = useContacts(search);
  const contacts = contactsQuery.data ?? [];

  const [open, setOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [editing, setEditing] = useState<CrmContact | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [origin, setOrigin] = useState("Manual");
  const [messagingChatId, setMessagingChatId] = useState("");
  const [budgetPerson, setBudgetPerson] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [importFeedback, setImportFeedback] = useState<string | null>(null);

  const messagingChatsQuery = useHubMessagingChats(open || importOpen);
  const messagingChats = messagingChatsQuery.data ?? [];

  function openNew() {
    setEditing(null);
    setName("");
    setPhone("");
    setEmail("");
    setCompany("");
    setOrigin("Manual");
    setMessagingChatId("");
    setBudgetPerson("");
    setTagsText("");
    setNotes("");
    setErr(null);
    setOpen(true);
  }

  function openEdit(c: CrmContact) {
    setEditing(c);
    setName(c.name);
    setPhone(c.phone_display || c.phone || "");
    setEmail(c.email || "");
    setCompany(c.company || "");
    setOrigin(c.origin || "Manual");
    setMessagingChatId(c.messaging_chat_id || "");
    setBudgetPerson(c.budget_person || "");
    setTagsText((c.tags || []).join(", "));
    setNotes(c.notes || "");
    setErr(null);
    setOpen(true);
  }

  const saveContact = useMutation({
    mutationFn: async () => {
      const payload = {
        name: name.trim(),
        phone: phone.trim() || undefined,
        email: email.trim() || undefined,
        company: company.trim() || undefined,
        origin: origin.trim() || "Manual",
        messaging_chat_id: messagingChatId || null,
        budget_person: budgetPerson.trim() || undefined,
        tags: tagsText
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        notes: notes.trim() || undefined,
      };
      if (editing) {
        return crmApi.updateContact(editing.id, payload);
      }
      return crmApi.createContact(payload);
    },
    onSuccess: () => {
      setOpen(false);
      setErr(null);
      void qc.invalidateQueries({ queryKey: ["crm", "contacts"] });
      void qc.invalidateQueries({ queryKey: ["crm", "dashboard"] });
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      announce(editing ? "Contato atualizado." : "Contato criado.");
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  const removeContact = useMutation({
    mutationFn: crmApi.deleteContact,
    onSuccess: () => {
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ["crm", "contacts"] });
      void qc.invalidateQueries({ queryKey: ["crm", "dashboard"] });
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      announce("Contato excluído.");
    },
  });

  const importChat = useMutation({
    mutationFn: crmApi.importFromMessaging,
    onSuccess: (res) => {
      setImportFeedback(
        res.created
          ? `"${res.contact.name}" importado da Mensageria.`
          : `"${res.contact.name}" já estava no CRM e foi vinculado.`,
      );
      void qc.invalidateQueries({ queryKey: ["crm", "contacts"] });
      void qc.invalidateQueries({ queryKey: ["crm", "dashboard"] });
      void qc.invalidateQueries({ queryKey: crmKeys.sources });
      announce("Contato sincronizado da Mensageria.");
    },
    onError: (e) => setImportFeedback(errorMessage(e)),
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    saveContact.mutate();
  }

  return (
    <div className="stack">
      <PageHeader
        title="Contatos"
        subtitle="Base unificada de clientes integrada à Mensageria e ao Meu Orçamento."
        actions={
          <>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => {
                setImportFeedback(null);
                setImportOpen(true);
              }}
            >
              <Download size={16} aria-hidden />
              Importar da Mensageria
            </button>
            <button type="button" className="btn btn--primary" onClick={openNew}>
              <Plus size={16} aria-hidden />
              Novo contato
            </button>
          </>
        }
      />

      <div className="list-tools list-tools--pills">
        <div className="list-tools__search">
        <Search size={16} aria-hidden />
        <label htmlFor="crm-contact-search" className="sr-only">
          Buscar contato
        </label>
        <input
          id="crm-contact-search"
          type="search"
          placeholder="Buscar contato..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        </div>
      </div>

      {contactsQuery.isPending ? (
        <div className="card">
          <p className="muted small">Carregando contatos…</p>
        </div>
      ) : contactsQuery.isError ? (
        <Alert tone="error">{errorMessage(contactsQuery.error)}</Alert>
      ) : contacts.length === 0 ? (
        <EmptyGuide icon={<UserRound size={28} />} title="Nenhum contato cadastrado ainda."
          text="Cadastre um contato ou importe uma conversa da Mensageria."
          action={<button type="button" className="btn btn--primary" onClick={openNew}>
            Cadastrar contato
          </button>} />
      ) : (
        <ul className="items">
          {contacts.map((c) => (
            <li key={c.id} className="item item--stack">
              <div className="item__main">
                <div>
                  <strong className="item__title">{c.name}</strong>
                  {c.company && <div className="muted small">{c.company}</div>}
                </div>
                {c.origin && <span className="badge badge--muted">{c.origin}</span>}
              </div>

              <div className="stack stack--tight small muted">
                {c.phone_display && <span>{c.phone_display}</span>}
                {c.email && <span>{c.email}</span>}
                {c.messaging_chat_id && (
                  <span className="row">
                    <MessageCircle size={13} aria-hidden />
                    Mensageria vinculada
                  </span>
                )}
                {c.budget_person && (
                  <span className="row">
                    <Wallet size={13} aria-hidden />
                    Orçamento: {c.budget_person}
                  </span>
                )}
              </div>

              {c.tags.length > 0 && (
                <div className="row">
                  {c.tags.map((tag) => (
                    <span key={tag} className="badge badge--accent">
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              <div className="form-actions">
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => openEdit(c)}>
                  Editar
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Janela: Criar / editar contato */}
      <Sheet
        open={open}
        title={editing ? "Editar contato" : "Novo contato"}
        onClose={() => setOpen(false)}
      >
        <form className="inline-form stack" onSubmit={onSubmit}>
          {err && (
            <Alert tone="error">
              {err}
            </Alert>
          )}
          <label className="field">
            <span className="field-label">Nome</span>
            <input type="text" required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <div className="grid-2">
            <label className="field">
              <span className="field-label">Telefone / WhatsApp</span>
              <input
                type="tel"
                placeholder="(11) 99999-9999"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">E-mail</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
          </div>
          <div className="grid-2">
            <label className="field">
              <span className="field-label">Empresa</span>
              <input type="text" value={company} onChange={(e) => setCompany(e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">Origem</span>
              <input type="text" value={origin} onChange={(e) => setOrigin(e.target.value)} />
            </label>
          </div>
          <div className="grid-2">
            <label className="field">
              <span className="field-label">Conversa na Mensageria</span>
              <select value={messagingChatId} onChange={(e) => setMessagingChatId(e.target.value)}>
                <option value="">Sem vínculo</option>
                {messagingChats.map((chat) => (
                  <option key={chat.id} value={chat.id}>
                    {chat.name}
                    {chat.phone_display ? ` (${chat.phone_display})` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Pessoa no Meu Orçamento</span>
              <input
                type="text"
                placeholder="Nome em Divisões/Empréstimos"
                value={budgetPerson}
                onChange={(e) => setBudgetPerson(e.target.value)}
              />
            </label>
          </div>
          <label className="field">
            <span className="field-label">Etiquetas (separadas por vírgula)</span>
            <input
              type="text"
              placeholder="VIP, recorrente"
              value={tagsText}
              onChange={(e) => setTagsText(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Observações</span>
            <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <div className="split">
            {editing ? (
              <button
                type="button"
                className="btn btn--danger btn--sm"
                onClick={() => removeContact.mutate(editing.id)}
              >
                <Trash2 size={15} aria-hidden />
                Excluir
              </button>
            ) : (
              <span />
            )}
            <div className="row">
              <button type="button" className="btn btn--secondary" onClick={() => setOpen(false)}>
                Cancelar
              </button>
              <button type="submit" className="btn btn--primary" disabled={saveContact.isPending}>
                {saveContact.isPending ? "Salvando…" : "Salvar"}
              </button>
            </div>
          </div>
        </form>
      </Sheet>

      {/* Janela: Importar contatos da Mensageria */}
      <Sheet
        open={importOpen}
        title="Importar da Mensageria"
        onClose={() => setImportOpen(false)}
      >
        <div className="stack">
          <p className="muted small">
            Escolha uma conversa do WhatsApp para cadastrar ou vincular ao CRM.
          </p>
          {importFeedback && (
            <Alert tone="success">
              {importFeedback}
            </Alert>
          )}
          {messagingChatsQuery.isPending ? (
            <p className="muted small">Carregando conversas…</p>
          ) : messagingChats.length === 0 ? (
            <p className="muted small">Nenhuma conversa encontrada na Mensageria ainda.</p>
          ) : (
            <ul className="items">
              {messagingChats.map((chat) => (
                <li
                  key={chat.id}
                  className="item"
                >
                  <div className="item__main">
                    <strong>{chat.name}</strong>
                    {chat.phone_display && <span className="muted small">{chat.phone_display}</span>}
                  </div>
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    disabled={importChat.isPending}
                    onClick={() => importChat.mutate(chat.id)}
                  >
                    Importar
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Sheet>
    </div>
  );
}
