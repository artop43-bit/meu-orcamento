import { describe, expect, it } from "vitest";

import {
  chatPhoneLabel,
  connectButtonLabel,
  contactInitials,
  dayKey,
  expandQuickReply,
  extractMoneyFromMessage,
  payloadForChat,
  followupStatus,
  formatAudioTime,
  formatBytes,
  formatChatTimestamp,
  formatMessageDay,
  groupMessagesByDay,
  hasVisiblePhone,
  HIDDEN_PHONE_LABEL,
  isPairingStatus,
  laterIso,
  mediaCaption,
  mergeMessages,
  messageStatusLabel,
  SERVICE_STATUS_LABELS,
  serviceStatusTone,
  sessionBadgeTone,
  sessionPollInterval,
  sessionStatusLabel,
  shortenPreview,
  snapshotFile,
  type MessagesState,
} from "./messaging";

describe("valores brasileiros e conteúdo por conversa", () => {
  it.each([
    ["R$ 1500", "1500.00"],
    ["R$ 2000,00", "2000.00"],
    ["R$ 1.500", "1500.00"],
    ["R$ 1234,56", "1234.56"],
    ["paguei 1.500 reais", "1500.00"],
    ["1,5 mil", "1500.00"],
    ["R$ 1.234,56", "1234.56"],
    ["R$ 12,50", "12.50"],
  ])("extrai %s sem perder dígitos", (text, expected) => {
    expect(extractMoneyFromMessage(text).amount).toBe(expected);
  });

  it("impede que anexo ou Pix sejam aplicados em outra conversa", () => {
    const attachment = { chatId: "a", file: "foto", seq: 1 };
    const pix = { chatId: "a", text: "Pix da pessoa A", seq: 2 };
    expect(payloadForChat(attachment, "a")).toBe(attachment);
    expect(payloadForChat(attachment, "b")).toBeNull();
    expect(payloadForChat(pix, "b")).toBeNull();
    expect(payloadForChat(null, "b")).toBeNull();
  });
});

describe("utilitários da Mensageria", () => {
  const now = new Date(2026, 10, 19, 15, 30, 0);

  it("formata datas da lista de conversas e separadores de dia", () => {
    const today = new Date(2026, 10, 19, 9, 15, 0).toISOString();
    const yesterday = new Date(2026, 10, 18, 18, 0, 0).toISOString();
    const older = new Date(2026, 10, 10, 12, 0, 0).toISOString();

    expect(formatMessageDay(today, now)).toBe("Hoje");
    expect(formatMessageDay(yesterday, now)).toBe("Ontem");
    expect(formatMessageDay(older, now)).toBe("10/11/2026");

    expect(formatChatTimestamp(yesterday, now)).toBe("Ontem");
    expect(formatChatTimestamp(older, now)).toBe("10/11");
    expect(dayKey(older)).toBe("2026-11-10");
  });

  it("encurta prévias longas com reticências e trata texto vazio", () => {
    expect(shortenPreview(null)).toBe("Sem mensagens");
    expect(shortenPreview("Oi, tudo bem?")).toBe("Oi, tudo bem?");
    const long = "Mensagem muito longa enviada pelo cliente para testar o resumo curto na lista lateral";
    const shortened = shortenPreview(long, 30);
    expect(shortened.length).toBeLessThanOrEqual(30);
    expect(shortened.endsWith("…")).toBe(true);
  });

  it("extrai iniciais e rótulos de status da mensagem", () => {
    expect(contactInitials("Carlos Silva")).toBe("CS");
    expect(contactInitials("Ana")).toBe("AN");
    expect(contactInitials("")).toBe("?");
    expect(messageStatusLabel("read")).toBe("Lida");
    expect(messageStatusLabel("pending")).toBe("Na fila");
  });

  it("agrupa mensagens por dia na ordem em que chegaram", () => {
    const groups = groupMessagesByDay(
      [
        { id: "1", created_at: new Date(2026, 10, 18, 10, 0).toISOString() },
        { id: "2", created_at: new Date(2026, 10, 18, 11, 0).toISOString() },
        { id: "3", created_at: new Date(2026, 10, 19, 8, 0).toISOString() },
      ],
      now,
    );
    expect(groups.map((g) => g.label)).toEqual(["Ontem", "Hoje"]);
    expect(groups[0].items.map((m) => m.id)).toEqual(["1", "2"]);
  });
});

describe("status da conexão com o WhatsApp", () => {
  it("tem um rótulo simples para cada status", () => {
    expect(sessionStatusLabel("disconnected")).toBe("Desconectado");
    expect(sessionStatusLabel("connecting")).toBe("Conectando");
    expect(sessionStatusLabel("qr")).toBe("Aguardando QR");
    expect(sessionStatusLabel("ready")).toBe("Conectado");
    expect(sessionStatusLabel("error")).toBe("Erro");
  });

  it("usa as cores de selo existentes", () => {
    expect(sessionBadgeTone("ready")).toBe("badge--ok");
    expect(sessionBadgeTone("connecting")).toBe("badge--warn");
    expect(sessionBadgeTone("qr")).toBe("badge--warn");
    expect(sessionBadgeTone("error")).toBe("badge--error");
    expect(sessionBadgeTone("disconnected")).toBe("badge--muted");
  });

  it("só pergunta a cada 2 s com a janela aberta e o pareamento em andamento", () => {
    expect(isPairingStatus("connecting")).toBe(true);
    expect(isPairingStatus("qr")).toBe(true);
    expect(isPairingStatus("ready")).toBe(false);
    expect(isPairingStatus(undefined)).toBe(false);

    expect(sessionPollInterval(true, "qr")).toBe(2_000);
    expect(sessionPollInterval(true, "connecting")).toBe(2_000);
    expect(sessionPollInterval(true, "ready")).toBe(10_000);
    expect(sessionPollInterval(true, undefined)).toBe(10_000);
    expect(sessionPollInterval(false, "qr")).toBe(10_000);
  });

  it("troca o texto do botão conforme o estado", () => {
    expect(connectButtonLabel("disconnected", null)).toBe("Conectar");
    expect(connectButtonLabel("disconnected", "O QR Code expirou. Gere um novo.")).toBe("Gerar novo QR");
    expect(connectButtonLabel("error", "Este número foi conectado em outro lugar.")).toBe("Tentar de novo");
  });
});

describe("número do contato", () => {
  it("mostra o número formatado ou avisa que o WhatsApp escondeu", () => {
    expect(chatPhoneLabel({ phone: "5511999999999", phone_display: "+55 (11) 99999-9999" })).toBe(
      "+55 (11) 99999-9999",
    );
    expect(chatPhoneLabel({ phone: null, phone_display: "" })).toBe(HIDDEN_PHONE_LABEL);
    expect(chatPhoneLabel({ phone: null, phone_display: null })).toBe("Número oculto pelo WhatsApp");
    expect(hasVisiblePhone({ phone: null, phone_display: "" })).toBe(false);
    expect(hasVisiblePhone({ phone: "5511999999999", phone_display: "+55 (11) 99999-9999" })).toBe(true);
  });
});

describe("mescla de mensagens do polling incremental", () => {
  type Msg = { id: string; created_at: string; updated_at: string; status: string };
  const msg = (id: string, created: string, updated: string, status = "sent"): Msg => ({
    id,
    created_at: `2026-11-19T10:${created}:00Z`,
    updated_at: `2026-11-19T10:${updated}:00Z`,
    status,
  });

  it("primeira carga guarda os itens e o cursor", () => {
    const state = mergeMessages<Msg>(undefined, [msg("a", "01", "01"), msg("b", "02", "02")], "2026-11-19T10:02:00Z");
    expect(state.items.map((m) => m.id)).toEqual(["a", "b"]);
    expect(state.cursor).toBe("2026-11-19T10:02:00Z");
  });

  it("substitui a mensagem atualizada, acrescenta a nova e mantém a ordem por created_at", () => {
    const current: MessagesState<Msg> = {
      items: [msg("a", "01", "01", "sent"), msg("b", "03", "03", "sent")],
      cursor: "2026-11-19T10:03:00Z",
    };
    const next = mergeMessages(
      current,
      [msg("b", "03", "05", "read"), msg("c", "04", "04", "delivered"), msg("old", "02", "02", "delivered")],
      "2026-11-19T10:05:00Z",
    );
    expect(next.items.map((m) => m.id)).toEqual(["a", "old", "b", "c"]);
    expect(next.items.find((m) => m.id === "b")?.status).toBe("read");
    expect(next.cursor).toBe("2026-11-19T10:05:00Z");
  });

  it("resposta atrasada não desfaz um status mais novo", () => {
    const current: MessagesState<Msg> = { items: [msg("a", "01", "06", "read")], cursor: "2026-11-19T10:06:00Z" };
    const next = mergeMessages(current, [msg("a", "01", "02", "sent")], "2026-11-19T10:02:00Z");
    expect(next.items[0].status).toBe("read");
    // O cursor nunca volta para trás.
    expect(next.cursor).toBe("2026-11-19T10:06:00Z");
  });

  it("mensagem enviada daqui entra sem mexer no cursor", () => {
    const current: MessagesState<Msg> = { items: [msg("a", "01", "01")], cursor: "2026-11-19T10:01:00Z" };
    const next = mergeMessages(current, [msg("mine", "09", "09", "pending")]);
    expect(next.items.map((m) => m.id)).toEqual(["a", "mine"]);
    expect(next.cursor).toBe("2026-11-19T10:01:00Z");

    // Sem nada carregado ainda: fica sem cursor, e o próximo pedido busca tudo.
    expect(mergeMessages<Msg>(undefined, [msg("mine", "09", "09")]).cursor).toBe("");
  });

  it("escolhe a data mais recente e ignora valores vazios", () => {
    expect(laterIso("2026-11-19T10:00:00Z", "2026-11-19T10:00:05Z")).toBe("2026-11-19T10:00:05Z");
    expect(laterIso("2026-11-19T10:00:05Z", "2026-11-19T10:00:00Z")).toBe("2026-11-19T10:00:05Z");
    expect(laterIso("", "2026-11-19T10:00:00Z")).toBe("2026-11-19T10:00:00Z");
    expect(laterIso("2026-11-19T10:00:00Z", null)).toBe("2026-11-19T10:00:00Z");
    expect(laterIso(undefined, null)).toBe("");
  });
});

describe("mídias da conversa", () => {
  it("extrai a legenda sem repetir o rótulo fixo da mídia", () => {
    expect(mediaCaption("📷 Foto", "image")).toBe("");
    expect(mediaCaption("📷 Foto · recibo", "image")).toBe("recibo");
    expect(mediaCaption("🎤 Áudio", "audio")).toBe("");
    expect(mediaCaption("📄 Documento · fatura.pdf", "document", "fatura.pdf")).toBe("");
    expect(mediaCaption("📄 Documento · fatura.pdf · pago", "document", "fatura.pdf")).toBe("pago");
    expect(mediaCaption("Texto normal", "chat")).toBe("Texto normal");
  });

  it("formata tamanho de arquivo", () => {
    expect(formatBytes(0)).toBe("");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(1_572_864)).toBe("1,5 MB");
  });

  it("copia o arquivo anexado para a memória preservando nome, tipo e bytes", async () => {
    const original = new File([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])], "foto.jpeg", {
      type: "image/jpeg",
    });
    const copy = await snapshotFile(original);
    expect(copy).not.toBe(original);
    expect(copy.name).toBe("foto.jpeg");
    expect(copy.type).toBe("image/jpeg");
    expect(copy.size).toBe(4);
    expect(Array.from(new Uint8Array(await copy.arrayBuffer()))).toEqual([0xff, 0xd8, 0xff, 0xd9]);
  });

  it("formata o tempo do player de áudio em m:ss com segurança contra NaN/Infinity", () => {
    expect(formatAudioTime(0)).toBe("0:00");
    expect(formatAudioTime(Number.NaN)).toBe("0:00");
    expect(formatAudioTime(Number.POSITIVE_INFINITY)).toBe("0:00");
    expect(formatAudioTime(-5)).toBe("0:00");
    expect(formatAudioTime(5)).toBe("0:05");
    expect(formatAudioTime(65.8)).toBe("1:05");
    expect(formatAudioTime(125)).toBe("2:05");
  });
});

describe("recursos CRM 360°, respostas rápidas e lançamento financeiro da Mensageria", () => {
  const now = new Date(2026, 10, 20, 14, 0, 0);

  it("calcula o estado visual do follow-up (atrasado, hoje ou futuro)", () => {
    expect(followupStatus(null, now)).toBeNull();
    const overdue = new Date(2026, 10, 20, 10, 0, 0).toISOString();
    expect(followupStatus(overdue, now)?.tone).toBe("overdue");
    expect(followupStatus(overdue, now)?.label).toContain("Follow-up atrasado");

    const today = new Date(2026, 10, 20, 18, 0, 0).toISOString();
    expect(followupStatus(today, now)?.tone).toBe("today");
    expect(followupStatus(today, now)?.label).toContain("Follow-up hoje");

    const tomorrow = new Date(2026, 10, 21, 9, 30, 0).toISOString();
    expect(followupStatus(tomorrow, now)?.tone).toBe("upcoming");
    expect(followupStatus(tomorrow, now)?.label).toContain("Follow-up amanhã");
  });

  it("interpola variáveis inteligentes nos modelos de resposta rápida", () => {
    const text = expandQuickReply(
      "Olá {nome}! Sua chave Pix é {chave_pix} para o saldo {valor_pendente} ({telefone}).",
      {
        nome: "Marina Costa",
        telefone: "+55 (11) 98888-7777",
        chave_pix: "financeiro@empresa.com",
        valor_pendente: "R$ 240,00",
      },
    );
    expect(text).toBe(
      "Olá Marina! Sua chave Pix é financeiro@empresa.com para o saldo R$ 240,00 (+55 (11) 98888-7777).",
    );
  });

  it("extrai valor, tipo (receita/despesa) e meio de pagamento de mensagens do WhatsApp", () => {
    const rec = extractMoneyFromMessage("Oi! Recebi R$ 1.250,50 do projeto no Pix", "Marina");
    expect(rec.amount).toBe("1250.50");
    expect(rec.kind).toBe("income");
    expect(rec.paymentMethod).toBe("pix");

    const exp = extractMoneyFromMessage("Paguei 89,90 no cartão de crédito do mercado", "Mercado");
    expect(exp.amount).toBe("89.90");
    expect(exp.kind).toBe("expense");
    expect(exp.paymentMethod).toBe("credit");
  });

  it("mapeia rótulos e tons de status de atendimento", () => {
    expect(SERVICE_STATUS_LABELS.open).toBe("Em aberto");
    expect(SERVICE_STATUS_LABELS.waiting).toBe("Aguardando cliente");
    expect(SERVICE_STATUS_LABELS.resolved).toBe("Resolvido");
    expect(serviceStatusTone("resolved")).toBe("badge--ok");
    expect(serviceStatusTone("waiting")).toBe("badge--warn");
    expect(serviceStatusTone("open")).toBe("badge--muted");
  });
});
