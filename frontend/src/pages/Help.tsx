import type { ReactNode } from "react";
import {
  Banknote,
  CalendarDays,
  ChartPie,
  CreditCard,
  Landmark,
  ListChecks,
  PlayCircle,
  Repeat,
  SlidersHorizontal,
  Tags,
  Target,
  Upload,
  Wallet,
} from "lucide-react";
import { Link } from "react-router";

import { openTour } from "../components/help";
import { Button, PageHeader } from "../components/ui";

type Topic = { icon: ReactNode; title: string; to: string; items: ReactNode[] };

const TOPICS: Topic[] = [
  {
    icon: <Wallet size={20} />,
    title: "Orçamento",
    to: "/orcamento",
    items: [
      "Receitas e despesas do mês, com saldo, comprometimento da receita e Insights.",
      "Despesas podem ser únicas, parceladas (informe o total da compra e o número de parcelas) ou recorrentes (mensal, bimestral, trimestral, semestral ou anual).",
      "Lançamento rápido: “mercado 120 pix ontem”, “geladeira 1800 em 10x crédito” ou “+ freelance 600” para receitas.",
      "Ao editar uma recorrência ou parcela, escolha entre alterar apenas o mês atual ou também os seguintes.",
      "“Selecionar” permite pagar, recategorizar ou excluir várias despesas de uma vez.",
      "Disponível hoje: saldo livre do mês dividido pelos dias restantes, com simulação de uma despesa extra.",
    ],
  },
  {
    icon: <CalendarDays size={20} />,
    title: "Calendário",
    to: "/calendario",
    items: [
      "Vencimentos, recebimentos, parcelas, faturas e despesas previstas por dia.",
      "Despesas previstas (IPVA, viagens) entram na projeção e são confirmadas com um toque quando ocorrem.",
      "Lembretes dos vencimentos dos próximos 7 dias.",
    ],
  },
  {
    icon: <ChartPie size={20} />,
    title: "Insights",
    to: "/analises",
    items: [
      "Resultado do mês com alertas e recomendações objetivas.",
      "Tendências, comparação entre meses, projeção de 12 meses e simulador de cenários.",
      "Análises personalizadas, que podem ser salvas e fixadas no resumo.",
    ],
  },
  {
    icon: <Landmark size={20} />,
    title: "Investimentos",
    to: "/investimentos",
    items: [
      "Carteira com rentabilidade; ativos com código e quantidade são atualizados pela cotação.",
      "Cotações: índices, moedas, criptoativos, destaques da B3, ficha de cada ativo e simulador de renda fixa.",
      "Conteúdo informativo; não constitui recomendação de investimento.",
    ],
  },
  {
    icon: <Banknote size={20} />,
    title: "Contas",
    to: "/contas",
    items: [
      "Saldo de cada conta bancária ou carteira, hoje e previsto para o fim do mês.",
      "Vincule despesas e receitas a uma conta e registre transferências entre contas.",
    ],
  },
  {
    icon: <CreditCard size={20} />,
    title: "Cartões",
    to: "/cartoes",
    items: [
      "Limite utilizado, faturas e melhor dia de compra.",
      "Compras no crédito são alocadas na fatura correta pelo dia de fechamento.",
      "O pagamento da fatura marca as compras como pagas, sem lançamento duplicado.",
    ],
  },
  {
    icon: <ListChecks size={20} />,
    title: "Para revisar",
    to: "/revisar",
    items: ["Despesas importadas de extratos aguardam conferência da categoria antes de entrar nas análises."],
  },
  {
    icon: <Target size={20} />,
    title: "Metas",
    to: "/metas",
    items: ["Defina valor e prazo; o app calcula o aporte mensal necessário e acompanha o progresso."],
  },
  {
    icon: <Repeat size={20} />,
    title: "Recorrências",
    to: "/ajustes/recorrencias",
    items: ["Lançamentos automáticos, custo mensal e anual das assinaturas e detecção de gastos recorrentes."],
  },
  {
    icon: <Tags size={20} />,
    title: "Categorias e regras",
    to: "/ajustes/categorias",
    items: ["Categorias, limites mensais e regras de classificação automática (ex.: contém “uber” → Transporte)."],
  },
  {
    icon: <Upload size={20} />,
    title: "Importar e exportar",
    to: "/ajustes/dados",
    items: ["Importação de extratos OFX/CSV e exportação em CSV, Excel, PDF e backup completo."],
  },
  {
    icon: <SlidersHorizontal size={20} />,
    title: "Preferências e atalhos",
    to: "/ajustes/preferencias",
    items: ["Tema, cor de destaque, tamanho do texto, densidade e modo privacidade (tecla P). Ctrl+K abre os comandos."],
  },
];

export default function Help() {
  return (
    <>
      <PageHeader
        title="Central de ajuda"
        subtitle="Visão geral de cada tela. Nos formulários, o ícone ⓘ explica cada campo."
        actions={
          <Button type="button" variant="secondary" onClick={openTour}>
            <PlayCircle size={16} /> Ver apresentação
          </Button>
        }
      />
      <div className="help-topics">
        {TOPICS.map((t) => (
          <section key={t.title} className="card stack help-topic">
            <h2>
              {t.icon} {t.title}
            </h2>
            <ul>
              {t.items.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
            <Link to={t.to} className="small">
              Abrir {t.title}
            </Link>
          </section>
        ))}
      </div>
    </>
  );
}
