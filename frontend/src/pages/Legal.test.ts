import { createElement, type ComponentType } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { ME_KEY } from "../api/auth";
import { Privacy, Terms } from "./Legal";

function renderLegal(Page: ComponentType, loggedIn = false): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(ME_KEY, loggedIn ? { id: "user-1", email: "teste@example.com" } : null);
  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client },
      createElement(MemoryRouter, null, createElement(Page)),
    ),
  );
}

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replaceAll("&amp;", "&")
    .replaceAll("&#x27;", "'")
    .replaceAll("&quot;", '"')
    .replace(/\s+/g, " ")
    .trim();
}

describe("Termos de uso e Política de privacidade", () => {
  it("exibe a versão vigente, soluções novas e os links obrigatórios em ambas as páginas", () => {
    const termsHtml = renderLegal(Terms);
    const privacyHtml = renderLegal(Privacy);
    const termsText = visibleText(termsHtml);
    const privacyText = visibleText(privacyHtml);

    expect(termsText).toContain("Versão 2026-11-21");
    expect(privacyText).toContain("Versão 2026-11-21");

    for (const solution of ["Cofre & Garantias", "Caderno & Conhecimento"]) {
      expect(termsText).toContain(solution);
      expect(privacyText).toContain(solution);
    }

    expect(termsHtml).toContain('href="/entrar"');
    expect(termsHtml).toContain('href="/privacidade"');
    expect(termsHtml).toContain('href="/seguranca"');

    expect(privacyHtml).toContain('href="/entrar"');
    expect(privacyHtml).toContain('href="/termos"');
    expect(privacyHtml).toContain('href="/seguranca"');
    expect(privacyHtml).toContain('href="/ajustes/dados?aba=exportar"');
    expect(privacyHtml).toContain('href="/ajustes/preferencias#privacidade"');

    expect(renderLegal(Terms, true)).toContain('href="/"');
    expect(renderLegal(Privacy, true)).toContain('href="/"');
  });

  it("unifica o aviso de mudanças nos Termos sem prometer aviso prévio antes de entrar em vigor (T1)", () => {
    const termsText = visibleText(renderLegal(Terms));
    const privacyText = visibleText(renderLegal(Privacy));

    expect(termsText).toContain("Quando houver mudança relevante, avisaremos por e-mail ou no aplicativo.");
    expect(termsText).not.toContain("antes de entrarem em vigor");
    expect(privacyText).not.toContain("antes de entrarem em vigor");
    expect(privacyText).toContain("Termos de uso");
  });

  it("informa corretamente todas as fontes de cotações e índices (T2)", () => {
    const privacyText = visibleText(renderLegal(Privacy));
    expect(privacyText).toContain(
      "Cotações e índices vêm de fontes públicas (Banco Central, brapi.dev, AwesomeAPI e CoinGecko). Elas recebem só o código do ativo, nunca dados da sua conta.",
    );
  });

  it("mantém os avisos obrigatórios de investimentos e segurança (T5)", () => {
    const termsText = visibleText(renderLegal(Terms));
    const privacyText = visibleText(renderLegal(Privacy));

    expect(termsText).toContain("As cotações podem ter atraso e não são recomendação de investimento.");
    expect(privacyText).toContain(
      "Usamos criptografia, backups criptografados e verificação em duas etapas, mas nenhum sistema é totalmente seguro.",
    );
  });

  it("detalha controlador, papel da administração, exclusão com WhatsApp, lacunas LGPD e redação (T3, T4, T6, T7, T8)", () => {
    const termsText = visibleText(renderLegal(Terms));
    const privacyText = visibleText(renderLegal(Privacy));

    expect(privacyText).toContain(
      "Se você usa o Hub para trabalho ou negócio (conversas, contatos, CRM, propostas, documentos de clientes), você é o responsável por esses dados perante a lei (controlador) e deve ter um motivo legítimo para guardá-los. O Hub apenas os guarda e organiza para você. O uso só pessoal e doméstico fica fora da LGPD.",
    );
    expect(privacyText).toContain("contagem numérica de lançamentos (sem valores nem descrições)");
    expect(privacyText).toContain(
      "A administração não vê o conteúdo dos seus lançamentos financeiros, conversas do WhatsApp, dados do CRM, documentos do Cofre nem notas do Caderno.",
    );
    expect(privacyText).toContain(
      "Antes de excluir a conta, desconecte o WhatsApp na Mensageria. Se não fizer isso, remova o aparelho conectado pelo próprio WhatsApp no celular.",
    );
    expect(privacyText).toContain(
      "Alguns serviços usados (e-mail, notificações do navegador, WhatsApp e fontes de cotação) podem processar dados fora do Brasil.",
    );
    expect(privacyText).toContain(
      "Evite guardar no Cofre e no Caderno dados sensíveis de outras pessoas (saúde, documentos de menores) sem motivo legítimo.",
    );
    expect(privacyText).toContain("As credenciais cadastradas ficam cifradas no Hub.");
    expect(privacyText).toContain("30 dias");
    expect(privacyText).toContain("90 dias");
    expect(privacyText).toContain("canal do encarregado (LGPD)");
    expect(privacyText).toContain("O Hub não usa inteligência artificial nem envia seus dados para serviços de IA.");
    expect(termsText).toContain("um e-mail válido que seja seu");
    expect(privacyText).toContain(
      "Conversas fixadas, com etiqueta, nota, retorno ou ligadas ao CRM continuam na lista, sem as mensagens antigas.",
    );
  });
});
