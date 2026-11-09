import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, Download, Share2, X } from "lucide-react";

import type { Retrospective } from "../api/profile";
import { fileUrl } from "../api/support";
import { monthLabel, percent } from "../lib/format";
import { Avatar } from "./media";
import { Button } from "./ui";

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

export function periodTitle(data: Retrospective): string {
  return data.period === "year" ? `Ano de ${data.start.slice(0, 4)}` : monthLabel(data.start.slice(0, 7));
}

type Slide = { kicker: string; big: string; text: string };

/** Destaques em frases curtas. Valores em reais só entram com "mostrar valores" ligado. */
export function slides(data: Retrospective): Slide[] {
  const values = data.show_values;
  const list: Slide[] = [];
  if (data.savings_rate !== null) {
    list.push({
      kicker: data.savings_rate >= 0 ? "Taxa de poupança" : "Resultado do período",
      big: percent(data.savings_rate),
      text:
        data.savings_rate >= 0
          ? `da renda ficou guardada${values ? ` · ${brl.format(Number(data.balance))}` : ""}.`
          : `das receitas: as despesas passaram da renda${values ? ` em ${brl.format(-Number(data.balance))}` : ""}.`,
    });
  }
  if (data.top_category) {
    list.push({
      kicker: "Categoria com maior gasto",
      big: data.top_category.name,
      text: `${data.top_category.share_pct !== null ? `${percent(data.top_category.share_pct)} das despesas` : "Maior parte das despesas"}${
        values ? ` · ${brl.format(Number(data.top_category.total))}` : ""
      }.`,
    });
  }
  if (data.most_saved_category) {
    list.push({
      kicker: "Onde mais economizou",
      big: data.most_saved_category.name,
      text: `Gasto menor que no período anterior${values ? ` · ${brl.format(Number(data.most_saved_category.saved))} a menos` : ""}.`,
    });
  }
  if (data.expenses_change_pct !== null) {
    const down = data.expenses_change_pct <= 0;
    list.push({
      kicker: "Despesas comparadas ao período anterior",
      big: `${down ? "−" : "+"}${percent(Math.abs(data.expenses_change_pct))}`,
      text: down ? "Despesas menores que no período anterior." : "Despesas maiores que no período anterior.",
    });
  }
  if (data.period === "year") {
    list.push({
      kicker: "Meses no azul",
      big: `${data.positive_months} de ${data.months_with_data}`,
      text: data.best_month
        ? `Melhor mês: ${monthLabel(data.best_month.month.slice(0, 7))}${values ? ` (${brl.format(Number(data.best_month.balance))})` : ""}.`
        : "Meses com receitas maiores que as despesas.",
    });
  }
  list.push({
    kicker: "Organização",
    big: `${data.entries} lançamentos`,
    text: data.goals_completed ? `${data.goals_completed} meta(s) concluída(s) até agora.` : "Registrados no período.",
  });
  return list;
}

// ---------------------------------------------------------------- imagem para compartilhar

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

function wrap(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, width: number, lineHeight: number): number {
  let line = "";
  let cursor = y;
  for (const word of text.split(" ")) {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width > width && line) {
      ctx.fillText(line, x, cursor);
      line = word;
      cursor += lineHeight;
    } else line = test;
  }
  if (line) ctx.fillText(line, x, cursor);
  return cursor + lineHeight;
}

/** Monta a imagem da retrospectiva (story 9:16 ou feed 1:1) só com o que a pessoa escolheu mostrar. */

/** Mistura a cor (#rrggbb) com preto: `keep` é a fração da cor que fica (como color-mix). */
export function darken(hex: string, keep: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1]!, 16);
  const part = (shift: number) => Math.round(((n >> shift) & 255) * keep).toString(16).padStart(2, "0");
  return `#${part(16)}${part(8)}${part(0)}`;
}

export async function renderShareImage(
  data: Retrospective,
  person: { name: string; avatarId: string | null },
  format: "story" | "square",
): Promise<Blob> {
  const W = 1080;
  const H = format === "story" ? 1920 : 1080;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d")!;
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#1f7a62";
  // v1.6: degradê inteiro na cor escolhida, escurecida para o texto branco ser legível com qualquer cor.
  const gradient = ctx.createLinearGradient(0, 0, W, H);
  gradient.addColorStop(0, darken(accent, 0.55));
  gradient.addColorStop(1, darken(accent, 0.25));
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, W, H);

  const pad = 90;
  let y = format === "story" ? 200 : 110;
  const avatar = person.avatarId ? await loadImage(fileUrl(person.avatarId)) : null;
  const size = format === "story" ? 180 : 130;
  ctx.save();
  ctx.beginPath();
  ctx.arc(pad + size / 2, y + size / 2, size / 2, 0, Math.PI * 2);
  ctx.closePath();
  ctx.fillStyle = "rgba(255,255,255,0.18)";
  ctx.fill();
  if (avatar) {
    ctx.clip();
    const scale = Math.max(size / avatar.width, size / avatar.height);
    ctx.drawImage(avatar, pad + size / 2 - (avatar.width * scale) / 2, y + size / 2 - (avatar.height * scale) / 2, avatar.width * scale, avatar.height * scale);
  } else {
    ctx.fillStyle = "#ffffff";
    ctx.font = `700 ${size * 0.42}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(person.name.slice(0, 1).toUpperCase(), pad + size / 2, y + size / 2);
  }
  ctx.restore();
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#ffffff";
  ctx.font = `700 ${format === "story" ? 64 : 52}px system-ui, sans-serif`;
  ctx.fillText(person.name.slice(0, 26), pad + size + 40, y + size / 2 - 6);
  ctx.font = `500 ${format === "story" ? 40 : 34}px system-ui, sans-serif`;
  ctx.fillStyle = "rgba(255,255,255,0.8)";
  ctx.fillText(`Retrospectiva · ${periodTitle(data)}`, pad + size + 40, y + size / 2 + 48);
  y += size + (format === "story" ? 120 : 70);

  const items = slides(data).slice(0, format === "story" ? 6 : 4);
  for (const item of items) {
    ctx.fillStyle = "rgba(255,255,255,0.75)";
    ctx.font = `600 ${format === "story" ? 34 : 28}px system-ui, sans-serif`;
    ctx.fillText(item.kicker.toUpperCase(), pad, y);
    y += format === "story" ? 78 : 62;
    ctx.fillStyle = "#ffffff";
    ctx.font = `800 ${format === "story" ? 76 : 58}px system-ui, sans-serif`;
    y = wrap(ctx, item.big, pad, y, W - pad * 2, format === "story" ? 84 : 64);
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.font = `400 ${format === "story" ? 36 : 30}px system-ui, sans-serif`;
    y = wrap(ctx, item.text, pad, y - (format === "story" ? 20 : 14), W - pad * 2, format === "story" ? 46 : 38);
    y += format === "story" ? 50 : 22;
  }

  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.font = `700 ${format === "story" ? 40 : 34}px system-ui, sans-serif`;
  ctx.fillText("Meu Orçamento", pad, H - (format === "story" ? 130 : 80));
  ctx.fillStyle = "rgba(255,255,255,0.7)";
  ctx.font = `400 ${format === "story" ? 32 : 28}px system-ui, sans-serif`;
  ctx.fillText(window.location.host, pad, H - (format === "story" ? 80 : 40));

  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Não foi possível gerar a imagem."))), "image/png"),
  );
}

export async function shareOrDownload(blob: Blob, name: string, share: boolean): Promise<"shared" | "downloaded"> {
  const file = new File([blob], name, { type: "image/png" });
  if (share && navigator.canShare?.({ files: [file] })) {
    await navigator.share({ files: [file], title: "Minha retrospectiva" });
    return "shared";
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
  return "downloaded";
}

// ---------------------------------------------------------------- telas (story)

/** Retrospectiva em tela cheia: toque à direita avança, à esquerda volta; setas e Esc no teclado. */
export function StoryViewer({
  data,
  person,
  onClose,
  footer,
}: {
  data: Retrospective;
  person: { name: string; avatarId: string | null };
  onClose: () => void;
  footer: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const items = slides(data);
  const total = items.length + 1; // + capa
  const [index, setIndex] = useState(0);

  useEffect(() => {
    ref.current?.showModal();
    const dialog = ref.current;
    return () => dialog?.close();
  }, []);

  function go(delta: number) {
    setIndex((i) => Math.min(total - 1, Math.max(0, i + delta)));
  }

  const slide = index === 0 ? null : items[index - 1];
  return (
    <dialog
      ref={ref}
      className="story"
      aria-label={`Retrospectiva · ${periodTitle(data)}`}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") go(1);
        if (e.key === "ArrowLeft") go(-1);
      }}
    >
      <div className="story__bars" aria-hidden>
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={i <= index ? "is-done" : undefined} />
        ))}
      </div>
      <button type="button" className="story__close icon-btn" onClick={onClose} aria-label="Fechar retrospectiva">
        <X size={22} />
      </button>
      <div className="story__body" aria-live="polite">
        {slide ? (
          <div className="story__slide" key={index}>
            <p className="story__kicker">{slide.kicker}</p>
            <p className="story__big">{slide.big}</p>
            <p className="story__text">{slide.text}</p>
          </div>
        ) : (
          <div className="story__slide story__cover" key="capa">
            <Avatar fileId={person.avatarId} name={person.name} size={112} className="story__avatar" />
            <p className="story__kicker">Retrospectiva</p>
            <p className="story__big">{periodTitle(data)}</p>
            <p className="story__text">{person.name}</p>
          </div>
        )}
        {index === total - 1 && <div className="story__footer">{footer}</div>}
      </div>
      <button type="button" className="story__tap story__tap--prev" onClick={() => go(-1)} aria-label="Anterior" disabled={index === 0}>
        <ChevronLeft size={28} aria-hidden />
      </button>
      <button type="button" className="story__tap story__tap--next" onClick={() => go(1)} aria-label="Próxima" disabled={index === total - 1}>
        <ChevronRight size={28} aria-hidden />
      </button>
      <p className="sr-only">
        Tela {index + 1} de {total}
      </p>
    </dialog>
  );
}

export function ShareButtons({ onExport }: { onExport: (format: "story" | "square", share: boolean) => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);
  const canShare = typeof navigator !== "undefined" && "share" in navigator;
  async function run(key: string, format: "story" | "square", share: boolean) {
    setBusy(key);
    try {
      await onExport(format, share);
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="share-buttons">
      {canShare && (
        <Button type="button" loading={busy === "share"} onClick={() => void run("share", "story", true)}>
          <Share2 size={16} /> Compartilhar
        </Button>
      )}
      <Button type="button" variant="secondary" loading={busy === "story"} onClick={() => void run("story", "story", false)}>
        <Download size={16} /> Baixar story (9:16)
      </Button>
      <Button type="button" variant="secondary" loading={busy === "square"} onClick={() => void run("square", "square", false)}>
        <Download size={16} /> Baixar feed (1:1)
      </Button>
    </div>
  );
}
