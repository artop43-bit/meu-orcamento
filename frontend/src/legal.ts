/**
 * Dados do responsável pelo serviço (o "controlador", na LGPD).
 *
 * PREENCHA ANTES DE ABRIR O CADASTRO AO PÚBLICO. Enquanto houver campos entre colchetes,
 * as páginas de Termos e Privacidade mostram um aviso de "rascunho".
 * Recomendado: revisão por um advogado antes do lançamento.
 */
export const LEGAL = {
  serviceName: "Meu Orçamento",
  controllerName: "[NOME DO RESPONSÁVEL OU DA EMPRESA]",
  controllerDocument: "[CPF OU CNPJ]",
  contactEmail: "[E-MAIL DE CONTATO]",
  forumCity: "[CIDADE/UF]",
  hostingProvider: "Oracle Cloud (região São Paulo)",
  emailProvider: "[PROVEDOR DE E-MAIL TRANSACIONAL]",
  // Mesmo valor de TERMS_VERSION no backend.
  version: "2026-10-16",
  updatedAt: "16 de outubro de 2026",
};

export const LEGAL_IS_DRAFT = Object.values(LEGAL).some((value) => value.includes("["));
