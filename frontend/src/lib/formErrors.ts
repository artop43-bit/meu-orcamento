/**
 * Mensagens de erro do próprio app, junto do campo, no lugar dos balões do navegador
 * ("Preencha este campo."). Vale para todos os formulários: ao tentar salvar, cada campo
 * com problema ganha uma mensagem que diz exatamente o que falta, a tela rola até o
 * primeiro e o cursor vai para ele. A mensagem some assim que o campo é corrigido.
 *
 * Campos que mostram os próprios erros (data, dia) têm `data-own-errors`: aqui só se
 * impede o balão e se leva o foco até eles.
 */

type Control = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

const ERROR_ATTR = "data-auto-error";

function fieldName(el: Control): string {
  const label = el.closest("label");
  const text =
    label?.querySelector(".field-label")?.textContent ??
    (label ? Array.from(label.childNodes).find((n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim())?.textContent : null) ??
    el.getAttribute("aria-label") ??
    (el.getAttribute("aria-labelledby") ? document.getElementById(el.getAttribute("aria-labelledby")!)?.textContent : null) ??
    (el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.textContent : null) ??
    "";
  return text.replace(/\(opcional\)/i, "").trim();
}

export function messageFor(el: Control): string {
  const v = el.validity;
  const name = fieldName(el);
  if (v.customError) return el.validationMessage;
  if (v.valueMissing) {
    if (el instanceof HTMLSelectElement) return name ? `Escolha uma opção em "${name}".` : "Escolha uma opção.";
    if (el instanceof HTMLInputElement && (el.type === "radio" || el.type === "checkbox")) return "Escolha uma opção.";
    return name ? `Preencha o campo "${name}".` : "Preencha este campo.";
  }
  if (v.tooShort) return `Use pelo menos ${(el as HTMLInputElement).minLength} caracteres.`;
  if (v.tooLong) return `Use no máximo ${(el as HTMLInputElement).maxLength} caracteres.`;
  if (v.rangeUnderflow || v.rangeOverflow) {
    const input = el as HTMLInputElement;
    return `Use um valor entre ${input.min || "o mínimo"} e ${input.max || "o máximo"}.`;
  }
  if (v.typeMismatch && el.type === "email") return "Informe um e-mail válido (ex.: nome@exemplo.com).";
  if (v.patternMismatch) return el.title || "Formato inválido.";
  if (v.stepMismatch || v.badInput) return "Valor inválido.";
  return "Confira este campo.";
}

function anchorFor(el: Control): Element {
  return el.closest(".date-field") ?? el.closest("label") ?? el.closest("fieldset") ?? el;
}

function show(el: Control) {
  const anchor = anchorFor(el);
  const id = `${el.id || el.name || "campo"}-erro-${Math.random().toString(36).slice(2, 7)}`;
  let note = anchor.querySelector<HTMLElement>(`[${ERROR_ATTR}]`);
  if (!note) {
    note = document.createElement("small");
    note.className = "field-error";
    note.setAttribute(ERROR_ATTR, "");
    note.setAttribute("role", "alert");
    note.id = id;
    if (anchor === el) el.insertAdjacentElement("afterend", note);
    else anchor.appendChild(note);
  }
  note.textContent = messageFor(el);
  el.setAttribute("aria-invalid", "true");
  const described = new Set((el.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean));
  described.add(note.id);
  el.setAttribute("aria-describedby", [...described].join(" "));
}

function clear(el: Control) {
  const note = anchorFor(el).querySelector<HTMLElement>(`[${ERROR_ATTR}]`);
  if (!note) return;
  const described = (el.getAttribute("aria-describedby") ?? "").split(" ").filter((x) => x && x !== note.id);
  if (described.length) el.setAttribute("aria-describedby", described.join(" "));
  else el.removeAttribute("aria-describedby");
  if (!el.hasAttribute("data-own-errors")) el.removeAttribute("aria-invalid");
  note.remove();
}

let focusedThisRound = false;

export function installFormErrors() {
  document.addEventListener(
    "invalid",
    (event) => {
      const el = event.target as Control;
      if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement)) return;
      event.preventDefault(); // sem balão do navegador
      if (!el.hasAttribute("data-own-errors")) show(el);
      if (!focusedThisRound) {
        // Primeiro campo com problema: rola até ele e coloca o cursor.
        focusedThisRound = true;
        queueMicrotask(() => {
          el.scrollIntoView({ block: "center", behavior: "smooth" });
          el.focus({ preventScroll: true });
          window.setTimeout(() => (focusedThisRound = false), 0);
        });
      }
    },
    true,
  );
  const recheck = (event: Event) => {
    const el = event.target as Control;
    if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement)) return;
    // validity é lida sem disparar o evento "invalid" (que mostraria erros enquanto digita).
    if (el.validity.valid) clear(el);
    else if (anchorFor(el).querySelector(`[${ERROR_ATTR}]`)) show(el);
  };
  document.addEventListener("input", recheck, true);
  document.addEventListener("change", recheck, true);
}
