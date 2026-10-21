/**
 * Lançamento por voz (v1.3): o microfone do navegador transcreve a fala e a frase passa pelo
 * mesmo leitor do lançamento rápido ("mercado 120 pix ontem"). Nada é salvo sem confirmação:
 * o texto entendido vai para o campo e a pessoa toca em "Lançar".
 *
 * Funciona no Chrome, no Edge, no Android e no iPhone (Safari). No Chrome, a transcrição é
 * feita pelo serviço de voz do Google, como em qualquer site que usa o microfone.
 */

type RecognitionEvent = { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> };
type Recognition = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
};
type RecognitionConstructor = new () => Recognition;

function constructor(): RecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function speechSupported(): boolean {
  return constructor() !== null;
}

const ERRORS: Record<string, string> = {
  "not-allowed": "O microfone está bloqueado. Libere o acesso ao microfone nas permissões do navegador.",
  "service-not-allowed": "O microfone está bloqueado. Libere o acesso ao microfone nas permissões do navegador.",
  "no-speech": "Não ouvimos nada. Toque no microfone e fale perto do aparelho.",
  "audio-capture": "Nenhum microfone encontrado neste aparelho.",
  network: "O reconhecimento de voz precisa de internet.",
};

/**
 * Começa a ouvir. `onText` recebe o texto (parcial enquanto fala, final no fim); `onEnd`
 * recebe uma mensagem de erro, se houver. Devolve a função que para de ouvir.
 */
export function listen(onText: (text: string, final: boolean) => void, onEnd: (error?: string) => void): () => void {
  const Ctor = constructor();
  if (!Ctor) {
    onEnd("Este navegador não tem reconhecimento de voz. Use o Chrome, o Edge ou o Safari.");
    return () => undefined;
  }
  const recognition = new Ctor();
  recognition.lang = "pt-BR";
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.continuous = false;
  let failure: string | undefined;
  recognition.onresult = (event) => {
    let text = "";
    let final = false;
    for (let i = 0; i < event.results.length; i++) {
      text += event.results[i][0].transcript;
      final = event.results[i].isFinal;
    }
    onText(normalizeSpoken(text), final);
  };
  recognition.onerror = (event) => {
    if (event.error !== "aborted") failure = ERRORS[event.error] ?? "Não foi possível usar o microfone agora.";
  };
  recognition.onend = () => onEnd(failure);
  recognition.start();
  return () => recognition.stop();
}

const WORDS: [RegExp, string][] = [
  // "23 reais e 50 centavos" → "23,50"; "50 centavos" → "0,50"
  [/(\d+)\s*reais?\s*e\s*(\d{1,2})\s*centavos?/gi, "$1,$2"],
  [/(?<![\d,])(\d{1,2})\s*centavos?/gi, "0,$1"],
  // "23 vírgula 50" → "23,50"
  [/(\d+)\s*v[íi]rgula\s*(\d+)/gi, "$1,$2"],
  // "em 10 vezes" → "em 10x"
  [/(\d+)\s*(vezes|parcelas)\b/gi, "$1x"],
  [/cart[ãa]o\s+de\s+d[ée]bito/gi, "débito"],
  [/cart[ãa]o\s+de\s+cr[ée]dito/gi, "crédito"],
  [/\b(via|pelo|pela)\s+(pix|d[ée]bito|cr[ée]dito|boleto|dinheiro)/gi, "$2"],
  [/\bem\s+dinheiro\b/gi, "dinheiro"],
  // "receita de freelance 600" → "+ freelance 600"
  [/^\s*(receita|entrada)\s+(de\s+)?/i, "+ "],
];

/** Ajusta o jeito de falar ao jeito de escrever do lançamento rápido. */
export function normalizeSpoken(text: string): string {
  let out = text.trim();
  for (const [pattern, replacement] of WORDS) out = out.replace(pattern, replacement);
  // "6,5" falado vira "6,50"
  out = out.replace(/(\d+),(\d)(?!\d)/g, "$1,$20");
  return out.replace(/\s+/g, " ").trim();
}
