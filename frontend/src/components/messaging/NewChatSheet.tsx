import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { errorMessage } from "../../api/client";
import { messagingApi, messagingKeys, useBudgetContext, type MessagingChat } from "../../api/messaging";
import { Sheet } from "../ui";

/** Janela "Nova conversa": telefone, nome e (opcional) a pessoa ligada no Meu Orçamento. */
export function NewChatSheet({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (chat: MessagingChat) => void;
}) {
  const queryClient = useQueryClient();
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [budgetPerson, setBudgetPerson] = useState("");
  const [error, setError] = useState<string | null>(null);
  const budgetCtx = useBudgetContext(null, open);

  useEffect(() => {
    // Erro da tentativa anterior não aparece ao abrir de novo (os campos digitados ficam).
    if (open) setError(null);
  }, [open]);

  const createChat = useMutation({
    mutationFn: messagingApi.createChat,
    onSuccess: (created) => {
      setPhone("");
      setName("");
      setBudgetPerson("");
      setError(null);
      queryClient.setQueryData(messagingKeys.chat(created.id), created);
      void queryClient.invalidateQueries({ queryKey: messagingKeys.chatLists });
      void queryClient.invalidateQueries({ queryKey: messagingKeys.session });
      onCreated(created);
    },
    onError: (err) => setError(errorMessage(err)),
  });

  function onSelectBudgetPerson(person: string) {
    setBudgetPerson(person);
    const match = budgetCtx.data?.contacts.find((c) => c.person === person);
    if (match) {
      if (!name.trim()) setName(match.person);
      if (!phone.trim() && match.phone) setPhone(match.phone);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    createChat.mutate({
      phone,
      name: name.trim() || undefined,
      budget_person: budgetPerson || undefined,
    });
  }

  return (
    <Sheet open={open} title="Nova conversa" onClose={onClose}>
      <form className="inline-form stack" onSubmit={submit}>
        {error && (
          <p className="alert alert--error m-0" role="alert">
            {error}
          </p>
        )}
        <label className="field">
          <span className="field-label">Telefone (com DDD)</span>
          <input
            type="tel"
            required
            placeholder="(11) 99999-9999"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
          />
        </label>
        <label className="field">
          <span className="field-label">Nome</span>
          <input
            type="text"
            placeholder="Nome do contato"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        {budgetCtx.data && budgetCtx.data.contacts.length > 0 && (
          <label className="field">
            <span className="field-label">Pessoa no Meu Orçamento (opcional)</span>
            <select value={budgetPerson} onChange={(event) => onSelectBudgetPerson(event.target.value)}>
              <option value="">Sem vínculo</option>
              {budgetCtx.data.contacts.map((contact) => (
                <option key={contact.person} value={contact.person}>
                  {contact.person}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="row row--right">
          <button type="button" className="btn btn--secondary" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={createChat.isPending}>
            {createChat.isPending ? "Abrindo…" : "Abrir conversa"}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
