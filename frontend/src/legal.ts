/**
 * Dados do responsável pelo serviço (o "controlador", na LGPD).
 *
 * PREENCHA ANTES DE ABRIR O CADASTRO AO PÚBLICO. Enquanto houver campos entre colchetes,
 * as páginas de Termos e Privacidade mostram um aviso de "rascunho".
 * Recomendado: revisão por um advogado antes do lançamento.
 */
export const LEGAL = {
  serviceName: "Meu Orçamento",
  controllerName: "Arthur Vinicius",
  // Sem CNPJ no momento: o responsável é identificado pelo nome e pelo e-mail de contato.
  controllerDocument: "",
  contactEmail: "meuorcamento.app99@gmail.com",
  forumCity: "Goiânia/GO",
  hostingProvider: "Oracle Cloud (região São Paulo)",
  emailProvider: "Google (Gmail)",
  // Mesmo valor de TERMS_VERSION no backend.
  version: "2026-10-16",
  updatedAt: "16 de outubro de 2026",
};

export const LEGAL_IS_DRAFT = Object.values(LEGAL).some((value) => value.includes("["));
