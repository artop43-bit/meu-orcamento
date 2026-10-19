import type { ReactNode } from "react";
import {
  CalendarDays,
  ChartPie,
  CreditCard,
  Landmark,
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
    title: "Orçamento do mês",
    to: "/orcamento",
    items: [
      <>
        <strong>Renda fixa</strong>: salário de R$ 3.200 todo dia 5 → tipo “Fixa”, repetir “Todo mês”, dia 5.
      </>,
      <>
        <strong>Renda variável</strong>: freela de R$ 600 → tipo “Variável”. A previsão usa a média dos últimos meses.
      </>,
      <>
        <strong>Conta do dia a dia</strong>: “Mercado” R$ 350, já paga, no Pix. A categoria é sugerida pelo nome.
      </>,
      <>
        <strong>Parcelada</strong>: TV de R$ 1.990 em 10x → “Parcelada”, 10 parcelas, “O valor digitado é: o total”.
      </>,
      <>
        <strong>Que se repete</strong>: IPTU a cada 3 meses, seguro anual → “Se repete” + frequência.
      </>,
      <>
        <strong>Mudou o valor?</strong> Edite e escolha “Só este mês” ou “Este e os próximos”.
      </>,
      <>Toque no ⧉ para duplicar uma conta, e use a busca e os filtros quando a lista crescer.</>,
      <>
        <strong>Lançar numa frase</strong>: no campo rápido do topo (ou Ctrl+K) escreva “mercado 120 pix ontem”, “tv 1990 10x
        crédito” ou “+ freela 600” (renda).
      </>,
      <>
        <strong>Várias de uma vez</strong>: “Selecionar” para pagar, mudar categoria ou excluir em lote; “Marcar todas como pagas”
        resolve as vencidas.
      </>,
      <>
        <strong>No celular</strong>: deslize a conta para a direita para pagar e para a esquerda para excluir (com Desfazer).
      </>,
      <>
        <strong>Quanto posso gastar hoje</strong>: o quadro ao lado divide o que sobra do mês pelos dias que faltam, já tirando
        contas e planejados.
      </>,
    ],
  },
  {
    icon: <CalendarDays size={20} />,
    title: "Calendário",
    to: "/calendario",
    items: [
      "Mostra por dia: contas a vencer, recebimentos, parcelas e gastos planejados (cada tipo com cor e ícone).",
      "“Planejar gasto”: aniversário, IPVA, viagem. Entra na previsão e no consultor antes de acontecer.",
      "Quando acontecer, abra o planejado e toque em “Lançar já paga” ou “Lançar a pagar”.",
      "No topo aparecem os lembretes dos próximos 7 dias.",
    ],
  },
  {
    icon: <ChartPie size={20} />,
    title: "Análise financeira",
    to: "/analises",
    items: [
      "Resumo com o consultor: explica o mês em linguagem simples e avisa o que merece atenção.",
      "Projeção: os próximos 12 meses com fixas, parcelas, planejados e a média da renda variável.",
      "Monte sua análise: escolha o que ver, o período e o tipo de gráfico, e salve.",
    ],
  },
  {
    icon: <Landmark size={20} />,
    title: "Investimentos e Mercado",
    to: "/investimentos",
    items: [
      "Minha carteira: cadastre cada investimento. Com código (PETR4, BTC) e quantidade, o valor vem da cotação.",
      "Marque a reserva de emergência para contar no score.",
      "Mercado: índices, dólar, cripto, maiores altas e baixas, ficha com gráfico e lista “Acompanhando”.",
      "Simulador de renda fixa: compare poupança, Tesouro Selic, CDB e LCI/LCA com as taxas de hoje.",
      "Tudo é informativo: o app não recomenda comprar ou vender.",
    ],
  },
  {
    icon: <CreditCard size={20} />,
    title: "Cartões de crédito",
    to: "/cartoes",
    items: [
      "Cadastre o cartão com o dia de fechamento e o de vencimento (estão no app do banco).",
      "Ao lançar com a forma de pagamento Crédito, escolha o cartão e a data da compra: ela vai para a fatura certa.",
      "Parcelas vão uma para cada fatura seguinte. O melhor dia de compra é o do fechamento.",
      "Pague a fatura marcando-a como paga; não lance o pagamento como outra conta (seria contar duas vezes).",
    ],
  },
  {
    icon: <SlidersHorizontal size={20} />,
    title: "Preferências e atalhos",
    to: "/preferencias",
    items: [
      "Tema claro ou escuro, cor de destaque, texto maior e modo compacto.",
      "Tecla P (ou o olho no topo) esconde os valores. Ctrl+Z desfaz a última exclusão ou alteração.",
      "Sugestões e problemas: “Enviar sugestão” no menu chega direto a quem faz o app.",
    ],
  },
  {
    icon: <Target size={20} />,
    title: "Metas",
    to: "/metas",
    items: ["Ex.: “Reserva de emergência” de R$ 10.000 até dezembro. Registre cada valor guardado (ou retirado)."],
  },
  {
    icon: <Repeat size={20} />,
    title: "Contas fixas",
    to: "/fixas",
    items: [
      "Lista tudo o que se repete. Daqui dá para encerrar, mudar valor ou frequência de uma vez.",
      "Mostra quanto as assinaturas custam por mês e por ano, e sugere virar fixa o que se repete todo mês.",
    ],
  },
  {
    icon: <Tags size={20} />,
    title: "Categorias",
    to: "/categorias",
    items: [
      "Crie as suas, marque o que é essencial e defina um limite por mês (o consultor avisa quando chega perto).",
      "Regras automáticas: “contém uber → Transporte” vale ao lançar, na sugestão e ao importar o extrato.",
    ],
  },
  {
    icon: <Upload size={20} />,
    title: "Importar e exportar",
    to: "/dados",
    items: ["Importe o extrato do banco (OFX/CSV) e baixe uma cópia completa dos seus dados quando quiser."],
  },
];

export default function Help() {
  return (
    <>
      <PageHeader
        title="Como usar"
        subtitle="Exemplos rápidos de cada tela. Em qualquer formulário, toque no ⓘ para ver uma dica."
        actions={
          <Button type="button" variant="secondary" onClick={openTour}>
            <PlayCircle size={16} /> Rever o tour
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
              Abrir {t.title.toLowerCase()} →
            </Link>
          </section>
        ))}
      </div>
    </>
  );
}
