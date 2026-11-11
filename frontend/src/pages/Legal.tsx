import type { ReactNode } from "react";
import { Link } from "react-router";

import { useMe } from "../api/auth";
import { LEGAL, LEGAL_IS_DRAFT } from "../legal";

function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  const { data: user } = useMe();
  return (
    <main className="container legal">
      <p>
        <Link to={user ? "/" : "/entrar"}>← Voltar</Link>
      </p>
      <h1>{title}</h1>
      <p className="muted small">
        Versão {LEGAL.version} · atualizada em {LEGAL.updatedAt}
      </p>
      {LEGAL_IS_DRAFT && (
        <div className="alert alert--error">
          Rascunho: os dados do responsável ainda não foram preenchidos (arquivo <code>frontend/src/legal.ts</code>).
        </div>
      )}
      {children}
    </main>
  );
}

export function Privacy() {
  return (
    <LegalPage title="Política de privacidade">
      <p>
        Esta política explica como o {LEGAL.serviceName} trata seus dados pessoais, de acordo com a Lei Geral de
        Proteção de Dados (Lei nº 13.709/2018, "LGPD").
      </p>

      <h2>1. Quem é o responsável</h2>
      <p>
        O controlador dos dados é {LEGAL.controllerName}
        {LEGAL.controllerDocument && ` (${LEGAL.controllerDocument})`}. Para qualquer assunto sobre
        seus dados, inclusive para falar com o encarregado, escreva para{" "}
        <strong>{LEGAL.contactEmail}</strong>.
      </p>

      <h2>2. Quais dados tratamos</h2>
      <ul>
        <li>
          <strong>Conta:</strong> e-mail e senha. A senha é guardada apenas como um resumo criptográfico (Argon2); nem
          nós conseguimos lê-la.
        </li>
        <li>
          <strong>Dados financeiros que você cadastra:</strong> rendas, contas, categorias, metas, investimentos e
          extratos que você importar.
        </li>
        <li>
          <strong>Segurança:</strong> endereço IP, navegador e data de logins, sessões e ações sensíveis (troca de
          senha, verificação em duas etapas). Se você ativar a verificação em duas etapas, guardamos a chave do
          aplicativo autenticador de forma criptografada.
        </li>
        <li>
          <strong>Registro do aceite</strong> destes termos (data e versão).
        </li>
      </ul>
      <p>
        Não pedimos documentos, dados bancários, senhas de banco nem acesso à sua conta bancária. Não usamos
        cookies de publicidade nem ferramentas de rastreamento: o único cookie é o de sessão, necessário para
        manter você conectado.
      </p>

      <h2>3. Para que usamos e com qual base legal</h2>
      <ul>
        <li>
          <strong>Prestar o serviço</strong> (guardar e calcular seu orçamento, enviar e-mails de confirmação e de
          recuperação de senha): execução de contrato (art. 7º, V).
        </li>
        <li>
          <strong>Proteger sua conta e o serviço</strong> (registros de acesso, limite de tentativas, prevenção a
          fraudes): legítimo interesse (art. 7º, IX) e cumprimento do Marco Civil da Internet (art. 15), que exige
          guardar registros de acesso por 6 meses.
        </li>
      </ul>
      <p>
        Seus dados financeiros <strong>não são vendidos, compartilhados para publicidade nem usados para traçar
        perfil</strong>. Os cálculos (score, projeções, dicas) são feitos só para mostrar a você.
      </p>

      <h2>4. Com quem compartilhamos</h2>
      <p>Apenas com fornecedores necessários para o serviço funcionar, que tratam os dados em nosso nome:</p>
      <ul>
        <li>
          <strong>Hospedagem:</strong> {LEGAL.hostingProvider}.
        </li>
        <li>
          <strong>Envio de e-mails:</strong> {LEGAL.emailProvider} (recebe apenas seu e-mail e o texto da
          mensagem).
        </li>
      </ul>
      <p>
        Os indicadores Selic, CDI e IPCA são consultados na API pública do Banco Central sem enviar nenhum dado seu.
        Também podemos compartilhar dados se uma autoridade exigir por lei ou ordem judicial.
      </p>

      <h2>5. Por quanto tempo guardamos</h2>
      <ul>
        <li>Dados da conta e financeiros: enquanto sua conta existir.</li>
        <li>Registros de segurança: 180 dias.</li>
        <li>Sessões e links de e-mail: apagados automaticamente após expirarem.</li>
        <li>
          Conversas do Tire sua dúvida: 30 dias depois da última mensagem. Você pode apagar antes ou desligar o histórico em{" "}
          <Link to="/ajustes/preferencias#privacidade">Preferências</Link>; as respostas são geradas no próprio site, sem enviar seus dados
          a terceiros.
        </li>
        <li>Backups do banco de dados: até 30 dias, depois são sobrescritos.</li>
      </ul>
      <p>Ao excluir a conta, seus dados são apagados na hora do banco principal e somem dos backups em até 30 dias.</p>

      <h2>6. Seus direitos</h2>
      <p>Você pode, a qualquer momento (art. 18 da LGPD):</p>
      <ul>
        <li>
          <strong>Acessar e levar seus dados:</strong> em <Link to="/dados">Dados → Backup completo</Link> você baixa
          tudo em JSON, e em CSV ou Excel.
        </li>
        <li>
          <strong>Corrigir:</strong> todos os dados podem ser editados no próprio app.
        </li>
        <li>
          <strong>Excluir:</strong> em <Link to="/seguranca">Segurança → Excluir conta</Link>, sem precisar pedir a
          ninguém.
        </li>
        <li>
          <strong>Saber com quem compartilhamos, revogar consentimentos, se opor a um tratamento</strong> ou fazer
          qualquer outra solicitação: escreva para {LEGAL.contactEmail}. Respondemos em até 15 dias.
        </li>
      </ul>
      <p>Você também pode reclamar à Autoridade Nacional de Proteção de Dados (ANPD).</p>

      <h2>7. Segurança</h2>
      <p>
        Usamos conexão criptografada (HTTPS), senhas com Argon2, verificação em duas etapas opcional, bloqueio após
        tentativas erradas, sessões que podem ser encerradas por você e backups criptografados. Nenhum sistema é
        100% seguro: se houver um incidente que possa trazer risco a você, avisaremos você e a ANPD.
      </p>

      <h2>8. Menores de idade</h2>
      <p>O serviço é destinado a maiores de 18 anos.</p>

      <h2>9. Mudanças nesta política</h2>
      <p>
        Se mudarmos algo importante, avisaremos por e-mail ou no próprio app antes de a mudança valer. A versão e a
        data estão no topo desta página.
      </p>
    </LegalPage>
  );
}

export function Terms() {
  return (
    <LegalPage title="Termos de uso">
      <p>
        Estes termos regem o uso do {LEGAL.serviceName}, oferecido por {LEGAL.controllerName}
        {LEGAL.controllerDocument && ` (${LEGAL.controllerDocument})`}. Ao criar uma conta, você concorda com eles e com a{" "}
        <Link to="/privacidade">Política de privacidade</Link>.
      </p>

      <h2>1. O serviço</h2>
      <p>
        O {LEGAL.serviceName} é uma ferramenta para organizar finanças pessoais: registrar rendas, contas, metas e
        investimentos e ver análises sobre eles. Os dados são informados por você.
      </p>

      <h2>2. Não é aconselhamento financeiro</h2>
      <p>
        Score, projeções, simulações, dicas e indicadores são <strong>estimativas informativas</strong> baseadas nos
        dados que você cadastra. Eles não são recomendação de investimento, consultoria financeira, contábil ou
        jurídica. Decisões financeiras são de sua responsabilidade.
      </p>

      <h2>3. Sua conta</h2>
      <ul>
        <li>Você precisa ter 18 anos ou mais e informar um e-mail válido que seja seu.</li>
        <li>
          Mantenha sua senha em segredo. Recomendamos ativar a verificação em duas etapas. Você é responsável pelo que
          for feito com sua conta.
        </li>
        <li>Avise-nos imediatamente em {LEGAL.contactEmail} se suspeitar de uso indevido.</li>
      </ul>

      <h2>4. Uso permitido</h2>
      <p>
        Não é permitido tentar acessar contas ou dados de outras pessoas, sobrecarregar ou atacar o serviço,
        automatizar acessos abusivos ou usá-lo para atividades ilegais. Podemos suspender contas que violem estas
        regras.
      </p>

      <h2>5. Seus dados são seus</h2>
      <p>
        Você pode exportar todos os seus dados e excluir sua conta a qualquer momento, pelo próprio app. Não
        reivindicamos nenhum direito sobre as informações que você cadastra.
      </p>

      <h2>6. Disponibilidade</h2>
      <p>
        Trabalhamos para manter o serviço no ar e fazemos backups diários, mas ele é oferecido "no estado em que se
        encontra", sem garantia de funcionamento ininterrupto. Recomendamos exportar seus dados de tempos em tempos.
      </p>

      <h2>7. Responsabilidade</h2>
      <p>
        Na máxima extensão permitida pela lei, não nos responsabilizamos por perdas decorrentes de decisões tomadas
        com base nas informações do app ou de dados cadastrados incorretamente. Nada aqui afasta direitos garantidos
        pelo Código de Defesa do Consumidor.
      </p>

      <h2>8. Encerramento</h2>
      <p>
        Você pode encerrar sua conta quando quiser em Segurança → Excluir conta. Se o serviço for descontinuado,
        avisaremos com pelo menos 30 dias de antecedência para que você exporte seus dados.
      </p>

      <h2>9. Mudanças</h2>
      <p>
        Podemos atualizar estes termos. Mudanças relevantes serão avisadas por e-mail ou no app antes de valerem.
      </p>

      <h2>10. Lei e foro</h2>
      <p>
        Estes termos seguem a lei brasileira. Fica eleito o foro de {LEGAL.forumCity}, sem prejuízo do direito do
        consumidor de escolher o foro do próprio domicílio.
      </p>
    </LegalPage>
  );
}
