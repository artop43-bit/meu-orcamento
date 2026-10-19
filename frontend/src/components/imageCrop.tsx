import { useEffect, useRef, useState, type PointerEvent } from "react";
import { ImagePlus, Trash2 } from "lucide-react";

import { errorMessage } from "../api/client";
import { checkImage, IMAGE_ACCEPT } from "../api/support";
import { Alert, Button, Sheet } from "./ui";

/** Foto: quadrada (vira círculo na tela). Banner: faixa 3:1. */
const SHAPES = {
  avatar: { ratio: 1, width: 512, height: 512, label: "foto" },
  banner: { ratio: 3, width: 1500, height: 500, label: "banner" },
} as const;

type Purpose = keyof typeof SHAPES;

const UNREADABLE = "Não foi possível abrir esta imagem. Escolha outra foto (PNG, JPG, WebP ou GIF).";

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Não foi possível gerar a imagem."))), "image/webp", 0.9);
  });
}

/**
 * Escolher, enquadrar e salvar a foto ou o banner. Imagens estáticas: arrastar para
 * posicionar e o controle de zoom para aproximar. GIF animado é enviado como está (o
 * enquadramento centralizado é feito na exibição, para não perder a animação).
 */
export function ImageEditor({
  purpose,
  open,
  hasImage,
  onClose,
  onSave,
  onRemove,
}: {
  purpose: Purpose;
  open: boolean;
  hasImage: boolean;
  onClose: () => void;
  onSave: (blob: Blob, name: string) => Promise<unknown>;
  onRemove: () => Promise<unknown>;
}) {
  const shape = SHAPES[purpose];
  const inputRef = useRef<HTMLInputElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const animated = file?.type === "image/gif";

  useEffect(() => {
    if (!open) {
      setFile(null);
      setError("");
    }
  }, [open]);

  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const next = URL.createObjectURL(file);
    setUrl(next);
    setZoom(1);
    setOffset({ x: 0, y: 0 });
    return () => URL.revokeObjectURL(next);
  }, [file]);

  function pick(list: FileList | null) {
    const chosen = list?.[0];
    if (inputRef.current) inputRef.current.value = "";
    if (!chosen) return;
    const problem = checkImage(chosen, purpose === "banner" ? 8 : 5);
    if (problem) {
      setError(problem);
      return;
    }
    setError("");
    setFile(chosen);
  }

  /** Tamanho da imagem na moldura (cobre a moldura inteira com zoom 1). */
  function layout() {
    const frame = frameRef.current;
    if (!frame || !natural) return null;
    const fw = frame.clientWidth;
    const fh = frame.clientHeight;
    const cover = Math.max(fw / natural.w, fh / natural.h) * zoom;
    return { fw, fh, w: natural.w * cover, h: natural.h * cover, scale: cover };
  }

  function clamp(x: number, y: number) {
    const l = layout();
    if (!l) return { x, y };
    const maxX = (l.w - l.fw) / 2;
    const maxY = (l.h - l.fh) / 2;
    return { x: Math.min(maxX, Math.max(-maxX, x)), y: Math.min(maxY, Math.max(-maxY, y)) };
  }

  useEffect(() => {
    setOffset((o) => clamp(o.x, o.y));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom, natural]);

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    if (animated) return;
    drag.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    setOffset(clamp(drag.current.ox + e.clientX - drag.current.x, drag.current.oy + e.clientY - drag.current.y));
  }

  async function save() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      if (animated) {
        await onSave(file, file.name);
      } else {
        const l = layout();
        if (!l) throw new Error(UNREADABLE);
        const image = new Image();
        image.src = url!;
        await image.decode().catch(() => {
          throw new Error(UNREADABLE);
        });
        const canvas = document.createElement("canvas");
        canvas.width = shape.width;
        canvas.height = shape.height;
        const ctx = canvas.getContext("2d")!;
        // Recorta o trecho visível da moldura, na resolução final.
        const scale = l.scale;
        const sx = (l.w / 2 - l.fw / 2 - offset.x) / scale;
        const sy = (l.h / 2 - l.fh / 2 - offset.y) / scale;
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(image, sx, sy, l.fw / scale, l.fh / scale, 0, 0, shape.width, shape.height);
        const blob = await canvasToBlob(canvas);
        // Safari não gera WebP: devolve PNG. O nome acompanha o tipo real.
        await onSave(blob, `${purpose}.${blob.type === "image/webp" ? "webp" : blob.type === "image/jpeg" ? "jpg" : "png"}`);
      }
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const l = url && natural ? layout() : null;
  return (
    <Sheet open={open} title={purpose === "avatar" ? "Foto do perfil" : "Banner do perfil"} onClose={onClose}>
      <div className="stack">
        <Alert tone="error">{error}</Alert>
        <input ref={inputRef} type="file" accept={IMAGE_ACCEPT} hidden onChange={(e) => pick(e.target.files)} aria-label={`Escolher ${shape.label}`} data-testid={`${purpose}-input`} />
        {url ? (
          <>
            <div
              ref={frameRef}
              className={`crop crop--${purpose} ${animated ? "crop--static" : ""}`}
              style={{ aspectRatio: String(shape.ratio) }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={() => (drag.current = null)}
              onPointerCancel={() => (drag.current = null)}
            >
              <img
                src={url}
                alt="Prévia"
                draggable={false}
                onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
                onError={() => setError(UNREADABLE)}
                style={
                  l && !animated
                    ? { width: l.w, height: l.h, transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px))` }
                    : undefined
                }
              />
            </div>
            {animated ? (
              <p className="muted small">GIF animado: a animação é mantida e a imagem é centralizada automaticamente.</p>
            ) : (
              <label>
                Zoom
                <input type="range" min={1} max={3} step={0.01} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} />
                <span className="muted small">Arraste a imagem para posicionar.</span>
              </label>
            )}
          </>
        ) : (
          <p className="muted">
            Escolha uma imagem ou GIF (PNG, JPG, WebP ou GIF, até {purpose === "banner" ? 8 : 5} MB). Você ajusta o enquadramento antes de salvar.
          </p>
        )}
        <div className="form-actions form-actions--split">
          {hasImage && !url && (
            <Button
              type="button"
              variant="danger"
              loading={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await onRemove();
                  onClose();
                } catch (err) {
                  setError(errorMessage(err));
                } finally {
                  setBusy(false);
                }
              }}
            >
              <Trash2 size={16} /> Remover
            </Button>
          )}
          <Button type="button" variant="secondary" onClick={() => inputRef.current?.click()}>
            <ImagePlus size={16} /> {url ? "Escolher outra" : "Escolher imagem"}
          </Button>
          {url && (
            <Button type="button" loading={busy} onClick={() => void save()}>
              Salvar
            </Button>
          )}
        </div>
      </div>
    </Sheet>
  );
}
