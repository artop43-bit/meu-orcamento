import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, X } from "lucide-react";

import { errorMessage } from "../../api/client";
import { messagingApi, messagingKeys, type QuickReply } from "../../api/messaging";
import { shortenPreview } from "../../lib/messaging";

/** Menu flutuante de respostas rápidas (`/` no Composer) com criação e exclusão de atalhos. */
export function QuickReplyMenu({
  replies,
  onSelect,
  onClose,
  onError,
}: {
  replies: QuickReply[];
  onSelect: (reply: QuickReply) => void;
  onClose: () => void;
  onError: (msg: string) => void;
}) {
  const qc = useQueryClient();
  const [addingQuick, setAddingQuick] = useState(false);
  const [newShortcut, setNewShortcut] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");

  const createQuickMutation = useMutation({
    mutationFn: () =>
      messagingApi.createQuickReply({
        shortcut: newShortcut,
        title: newTitle,
        body: newBody,
      }),
    onSuccess: () => {
      setNewShortcut("");
      setNewTitle("");
      setNewBody("");
      setAddingQuick(false);
      void qc.invalidateQueries({ queryKey: messagingKeys.quickReplies });
    },
    onError: (err) => onError(errorMessage(err)),
  });

  const deleteQuickMutation = useMutation({
    mutationFn: (id: string) => messagingApi.deleteQuickReply(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: messagingKeys.quickReplies });
    },
  });

  return (
    <div className="wa-quick-menu" role="dialog" aria-label="Respostas rápidas">
      <div className="wa-quick-menu__head">
        <span className="small">
          <strong>Respostas rápidas</strong>{" "}
          <span className="muted">(digite / ou escolha um modelo)</span>
        </span>
        <div className="row row--tight">
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setAddingQuick((v) => !v)}
          >
            <Plus size={13} aria-hidden />
            {addingQuick ? "Cancelar" : "Novo atalho"}
          </button>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="Fechar respostas rápidas"
          >
            <X size={15} aria-hidden />
          </button>
        </div>
      </div>

      {addingQuick && (
        <div className="wa-quick-menu__form">
          <div className="wa-quick-menu__form-row">
            <input
              type="text"
              className="input"
              placeholder="Atalho (ex.: agenda)"
              aria-label="Atalho da resposta rápida"
              value={newShortcut}
              maxLength={40}
              onChange={(e) => setNewShortcut(e.target.value)}
            />
            <input
              type="text"
              className="input"
              placeholder="Título curto"
              aria-label="Título da resposta rápida"
              value={newTitle}
              maxLength={80}
              onChange={(e) => setNewTitle(e.target.value)}
            />
          </div>
          <textarea
            className="input"
            rows={2}
            placeholder="Texto da mensagem. Variáveis: {nome}, {telefone}, {chave_pix}, {valor_pendente}"
            aria-label="Texto da resposta rápida"
            value={newBody}
            maxLength={2000}
            onChange={(e) => setNewBody(e.target.value)}
          />
          <div className="row row--between">
            <span className="muted small">
              Variáveis: <code>{"{nome}"}</code> <code>{"{chave_pix}"}</code>{" "}
              <code>{"{valor_pendente}"}</code>
            </span>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={
                !newShortcut.trim() ||
                !newTitle.trim() ||
                !newBody.trim() ||
                createQuickMutation.isPending
              }
              onClick={() => createQuickMutation.mutate()}
            >
              Salvar atalho
            </button>
          </div>
        </div>
      )}

      <div className="wa-quick-menu__list">
        {replies.map((item) => (
          <div key={item.id} className="wa-quick-menu__item">
            <button
              type="button"
              className="wa-quick-menu__pick"
              onClick={() => onSelect(item)}
            >
              <div className="wa-quick-menu__item-top">
                <code className="wa-quick-menu__code">{item.shortcut}</code>
                <strong className="small">{item.title}</strong>
              </div>
              <span className="muted small wa-quick-menu__preview">
                {shortenPreview(item.body, 88)}
              </span>
            </button>
            <button
              type="button"
              className="icon-btn wa-quick-menu__del"
              onClick={() => deleteQuickMutation.mutate(item.id)}
              aria-label={`Excluir atalho ${item.shortcut}`}
              title="Excluir atalho"
            >
              <Trash2 size={13} aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
