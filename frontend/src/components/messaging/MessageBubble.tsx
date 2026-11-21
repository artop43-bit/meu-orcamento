import {
  AlertCircle,
  CalendarPlus,
  Check,
  CheckCheck,
  Clock,
  Copy,
  Download,
  FileText,
  Mic,
  Pause,
  Play,
  Reply,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { MessagingMessage } from "../../api/messaging";
import {
  formatAudioTime,
  formatBytes,
  formatTime,
  mediaCaption,
  messageStatusLabel,
  shortenPreview,
} from "../../lib/messaging";

const PLAYBACK_RATES = [1, 1.5, 2] as const;

/**
 * Copia uma imagem da conversa para a área de transferência do sistema (Ctrl+C / Colar),
 * convertendo para PNG via canvas para compatibilidade total com `ClipboardItem`.
 */
export async function copyImageUrlToClipboard(url: string): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
    return false;
  }
  try {
    const res = await fetch(url, { credentials: "include" });
    if (!res.ok) return false;
    const blob = await res.blob();
    if (blob.type === "image/png") {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      return true;
    }
    const bitmapUrl = URL.createObjectURL(blob);
    try {
      const pngBlob = await new Promise<Blob | null>((resolve) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement("canvas");
          canvas.width = img.naturalWidth || img.width || 512;
          canvas.height = img.naturalHeight || img.height || 512;
          const ctx = canvas.getContext("2d");
          if (!ctx) {
            resolve(null);
            return;
          }
          ctx.drawImage(img, 0, 0);
          canvas.toBlob((out) => resolve(out), "image/png");
        };
        img.onerror = () => resolve(null);
        img.src = bitmapUrl;
      });
      if (!pngBlob) return false;
      await navigator.clipboard.write([new ClipboardItem({ "image/png": pngBlob })]);
      return true;
    } finally {
      URL.revokeObjectURL(bitmapUrl);
    }
  } catch {
    return false;
  }
}

export function MessageTick({ status }: { status: MessagingMessage["status"] }) {
  const label = messageStatusLabel(status);
  if (status === "pending") return <Clock size={13} className="wa-tick" aria-label={label} />;
  if (status === "failed") return <AlertCircle size={13} className="wa-tick wa-tick--error" aria-label={label} />;
  if (status === "read") return <CheckCheck size={14} className="wa-tick wa-tick--read" aria-label={label} />;
  if (status === "delivered") return <CheckCheck size={14} className="wa-tick" aria-label={label} />;
  return <Check size={14} className="wa-tick" aria-label={label} />;
}

function AudioPlayer({
  url,
  fileName,
  sizeBytes,
}: {
  url: string;
  fileName?: string | null;
  sizeBytes?: number | null;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const probingDurationRef = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rateIndex, setRateIndex] = useState(0);
  const [loadError, setLoadError] = useState(false);

  const rate = PLAYBACK_RATES[rateIndex];

  useEffect(() => {
    setPlaying(false);
    setCurrentTime(0);
    setDuration(0);
    setLoadError(false);
    probingDurationRef.current = false;
  }, [url]);

  function syncDuration(el: HTMLAudioElement) {
    const d = el.duration;
    if (Number.isFinite(d) && d > 0) {
      setDuration(d);
      if (probingDurationRef.current) {
        probingDurationRef.current = false;
        el.currentTime = 0;
      }
    } else if (d === Number.POSITIVE_INFINITY && !probingDurationRef.current) {
      // Áudios WebM/Opus gravados no navegador podem vir sem duração no cabeçalho; força o cálculo.
      probingDurationRef.current = true;
      try {
        el.currentTime = 1e101;
      } catch {
        probingDurationRef.current = false;
      }
    }
  }

  async function togglePlay() {
    const el = audioRef.current;
    if (!el) return;
    if (playing) {
      el.pause();
      setPlaying(false);
      return;
    }
    try {
      setLoadError(false);
      el.playbackRate = rate;
      await el.play();
      setPlaying(true);
    } catch {
      setPlaying(false);
      setLoadError(true);
    }
  }

  function cycleRate() {
    const nextIdx = (rateIndex + 1) % PLAYBACK_RATES.length;
    setRateIndex(nextIdx);
    if (audioRef.current) {
      audioRef.current.playbackRate = PLAYBACK_RATES[nextIdx];
    }
  }

  function handleSeek(nextValue: number) {
    const el = audioRef.current;
    setCurrentTime(nextValue);
    if (el && Number.isFinite(nextValue)) {
      try {
        el.currentTime = nextValue;
      } catch {
        // Ignora seek se o buffer ainda não estiver pronto.
      }
    }
  }

  const sizeLabel = formatBytes(sizeBytes);
  const timeText =
    duration > 0
      ? `${formatAudioTime(currentTime)} / ${formatAudioTime(duration)}`
      : currentTime > 0
        ? formatAudioTime(currentTime)
        : sizeLabel || "0:00";

  return (
    <div className="wa-audio-player" role="group" aria-label="Player de áudio da mensagem">
      <audio
        ref={audioRef}
        src={url}
        preload="metadata"
        onLoadedMetadata={(e) => syncDuration(e.currentTarget)}
        onDurationChange={(e) => syncDuration(e.currentTarget)}
        onTimeUpdate={(e) => {
          if (probingDurationRef.current) {
            syncDuration(e.currentTarget);
            return;
          }
          setCurrentTime(e.currentTarget.currentTime || 0);
          if (Number.isFinite(e.currentTarget.duration) && e.currentTarget.duration > 0) {
            setDuration(e.currentTarget.duration);
          }
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={(e) => {
          setPlaying(false);
          if (e.currentTarget.currentTime > 0 && duration === 0) {
            setDuration(e.currentTarget.currentTime);
          }
          setCurrentTime(0);
        }}
        onError={() => {
          setPlaying(false);
          setLoadError(true);
        }}
      />
      <button
        type="button"
        className="wa-audio-player__play"
        onClick={() => void togglePlay()}
        aria-label={playing ? "Pausar áudio" : "Ouvir áudio"}
        title={playing ? "Pausar" : "Ouvir"}
      >
        {playing ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden />}
      </button>

      <div className="wa-audio-player__main">
        <input
          type="range"
          className="wa-audio-player__range"
          min={0}
          max={duration > 0 ? duration : Math.max(currentTime, 1)}
          step={0.1}
          value={Math.min(currentTime, duration > 0 ? duration : Math.max(currentTime, 1))}
          onChange={(e) => handleSeek(Number.parseFloat(e.target.value))}
          aria-label="Posição do áudio"
        />
        <div className="wa-audio-player__meta">
          <span className="wa-audio-player__time">
            <Mic size={11} aria-hidden />
            {loadError ? "Toque em baixar para ouvir" : timeText}
          </span>
          <div className="wa-audio-player__actions">
            <button
              type="button"
              className="wa-audio-player__speed"
              onClick={cycleRate}
              aria-label={`Velocidade do áudio ${rate}x`}
              title="Mudar velocidade (1x / 1.5x / 2x)"
            >
              {rate}x
            </button>
            <a
              href={url}
              download={fileName ?? "audio.ogg"}
              className="wa-audio-player__dl"
              aria-label="Baixar áudio"
              title="Baixar áudio"
            >
              <Download size={13} aria-hidden />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Um balão de mensagem (texto ou mídia: foto, áudio, vídeo, figurinha e documento). */
export function MessageBubble({
  message,
  onReply,
  onZoomImage,
  onLaunchBudget,
  onWorkAction,
  onSaveToVault,
}: {
  message: MessagingMessage;
  onReply: (message: MessagingMessage) => void;
  onZoomImage?: (media: { url: string; alt: string; fileName?: string | null }) => void;
  onLaunchBudget?: (message: MessagingMessage) => void;
  onWorkAction?: (message: MessagingMessage) => void;
  onSaveToVault?: (message: MessagingMessage) => void;
}) {
  const [copiedImg, setCopiedImg] = useState(false);
  const out = message.direction === "out";
  const hasMedia = Boolean(message.media_url);
  const isAudioMsg = message.message_type === "audio";
  const caption =
    hasMedia || isAudioMsg
      ? mediaCaption(message.body, message.message_type, message.media_name)
      : message.body;

  async function handleCopyImage() {
    if (!message.media_url) return;
    const ok = await copyImageUrlToClipboard(message.media_url);
    if (ok) {
      setCopiedImg(true);
      window.setTimeout(() => setCopiedImg(false), 2000);
    }
  }

  function renderMedia() {
    if (!message.media_url) {
      if (isAudioMsg) {
        return (
          <div className="wa-audio-unavailable" role="note">
            <Mic size={15} aria-hidden />
            <span>Áudio antigo do histórico (mídia não sincronizada pelo celular)</span>
          </div>
        );
      }
      return null;
    }
    if (message.message_type === "image" || message.message_type === "sticker") {
      const isSticker = message.message_type === "sticker";
      const alt = caption || (isSticker ? "Figurinha" : "Foto");
      return (
        <div className="wa-media-img-wrap">
          <button
            type="button"
            className="wa-media-img-btn"
            onClick={() => onZoomImage?.({ url: message.media_url!, alt, fileName: message.media_name })}
            aria-label={`Ampliar ${alt}`}
          >
            <img
              src={message.media_url}
              alt={alt}
              className={isSticker ? "wa-media-sticker" : "wa-media-img"}
              loading="lazy"
            />
          </button>
          <div className="wa-media-img-tools">
            <button
              type="button"
              className="wa-media-tool-btn"
              onClick={() => void handleCopyImage()}
              aria-label="Copiar imagem"
              title="Copiar imagem para a área de transferência"
            >
              {copiedImg ? <Check size={12} aria-hidden /> : <Copy size={12} aria-hidden />}
              <span>{copiedImg ? "Copiada" : "Copiar"}</span>
            </button>
            <a
              href={message.media_url}
              download={message.media_name ?? (isSticker ? "figurinha.webp" : "foto.jpg")}
              className="wa-media-tool-btn"
              aria-label={`Baixar ${alt}`}
              title="Baixar imagem"
            >
              <Download size={12} aria-hidden />
              <span>Baixar</span>
            </a>
          </div>
        </div>
      );
    }
    if (message.message_type === "audio") {
      return (
        <AudioPlayer
          url={message.media_url}
          fileName={message.media_name}
          sizeBytes={message.media_size}
        />
      );
    }
    if (message.message_type === "video") {
      return (
        <video
          controls
          preload="metadata"
          src={message.media_url}
          className="wa-media-video"
          aria-label={caption || "Vídeo da mensagem"}
        />
      );
    }
    const sizeText = formatBytes(message.media_size);
    return (
      <div className="wa-media-doc">
        <span className="wa-media-doc__icon" aria-hidden>
          <FileText size={18} />
        </span>
        <span className="wa-media-doc__info">
          <strong className="small wa-media-doc__name">{message.media_name || "Documento"}</strong>
          {sizeText && <span className="muted small">{sizeText}</span>}
        </span>
        <a
          href={message.media_url}
          download={message.media_name ?? "documento"}
          className="btn btn--secondary btn--sm"
          aria-label={`Baixar ${message.media_name || "documento"}`}
        >
          <Download size={14} aria-hidden />
          Baixar
        </a>
      </div>
    );
  }

  return (
    <div className={`wa-msg-row ${out ? "wa-msg-row--out" : "wa-msg-row--in"}`}>
      <div className={`wa-msg ${out ? "wa-msg--out" : "wa-msg--in"} ${isAudioMsg ? "wa-msg--audio" : ""}`}>
        {message.reply_preview && (
          <div className="wa-msg__quote">
            <span className="small">{shortenPreview(message.reply_preview, 80)}</span>
          </div>
        )}
        {renderMedia()}
        {caption && <p className="wa-msg__body bubble__text">{caption}</p>}
        <div className="wa-msg__foot">
          <button
            type="button"
            className="wa-msg__reply-btn"
            onClick={() => onReply(message)}
            aria-label="Responder mensagem"
            title="Responder"
          >
            <Reply size={13} aria-hidden />
          </button>
          {onLaunchBudget && (
            <button
              type="button"
              className="wa-msg__reply-btn"
              onClick={() => onLaunchBudget(message)}
              aria-label="Lançar no Meu Orçamento"
              title="Lançar receita ou despesa no Meu Orçamento"
            >
              <Wallet size={13} aria-hidden />
            </button>
          )}
          {onWorkAction && (
            <button
              type="button"
              className="wa-msg__reply-btn"
              onClick={() => onWorkAction(message)}
              aria-label="Criar tarefa ou compromisso"
              title="Transformar em tarefa ou compromisso na Agenda"
            >
              <CalendarPlus size={13} aria-hidden />
            </button>
          )}
          {onSaveToVault &&
            message.media_id &&
            (message.message_type === "image" || message.message_type === "document") && (
              <button
                type="button"
                className="wa-msg__reply-btn"
                onClick={() => onSaveToVault(message)}
                aria-label="Guardar mídia no Cofre permanente"
                title="Guardar no Cofre (protege da limpeza semanal)"
              >
                <ShieldCheck size={13} aria-hidden />
              </button>
            )}
          <span className="wa-msg__time">{formatTime(message.created_at)}</span>
          {out && <MessageTick status={message.status} />}
        </div>
      </div>
    </div>
  );
}
