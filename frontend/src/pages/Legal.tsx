import type { ReactNode } from "react";
import { Link } from "react-router";

import { useMe } from "../api/auth";
import { LEGAL, LEGAL_IS_DRAFT } from "../legal";

function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  const { data: user } = useMe();
  return (
    <main className="container legal">
      <p><Link to={user ? "/" : "/entrar"}>← Voltar</Link></p>
      <h1>{title}</h1>
      <p className="muted small">Versão {LEGAL.version} · atualizada em {LEGAL.updatedAt}</p>
      {LEGAL_IS_DRAFT && (
        <div className="alert alert--error">Rascunho. A identificação do responsável ainda está incompleta.</div>
      )}
      {children}
    </main>
  );
}

function Controller() {
  return <>{LEGAL.controllerName}{LEGAL.controllerDocument && ` (${LEGAL.controllerDocument})`}</>;
}

function Contact() {
  return <a href={`mailto:${LEGAL.contactEmail}`}>{LEGAL.contactEmail}</a>;
}

export function Privacy() {
  return (
    <LegalPage title="Política de privacidade">
      <p>
        Esta política vale para o {LEGAL.serviceName} e suas soluções. Ela explica como tratamos dados pessoais
        conforme a Lei Geral de Proteção de Dados (Lei nº 13.709/2018, LGPD).
      </p>

      <h2>1. Quem é o responsável pelos dados</h2>
      <p>
        O responsável pelo tratamento dos dados da conta e pela operação do Hub é <Controller />.
        Para dúvidas ou solicitações sobre privacidade, escreva para <Contact />.
        Se você usa o Hub para gerir um negócio ou atender clientes, também pode ter responsabilidades
        sobre os dados de terceiros que cadastrar, inclusive informar essas pessoas quando necessário.
      </p>

      <h2>2. Quais dados usamos e para quê</h2>
      <ul>
        <li>
          <strong>Conta, segurança e suporte.</strong> Usamos seu e-mail, senha, dados de perfil, preferências
          e o registro da versão dos Termos aceitos. Registramos informações como IP, navegador, data de acesso,
          ações de segurança e dados técnicos de erros. Tratamos as mensagens e os anexos que você enviar ao suporte.
        </li>
        <li>
          <strong>Meu Orçamento.</strong> Usamos lançamentos, contas, cartões, metas, investimentos, pessoas
          vinculadas a divisões ou empréstimos e arquivos como extratos e comprovantes. O Tire sua dúvida usa
          os registros da conta e as perguntas que você fizer. A Reforma Tributária processa as informações
          da operação e o XML que você enviar para gerar DANFSe.
        </li>
        <li>
          <strong>Mensageria.</strong> Se você conectar o WhatsApp, tratamos dados de conexão, contatos,
          números, nomes, fotos de perfil, mensagens, mídias e informações de atendimento, como etiquetas,
          notas e lembretes de retorno.
        </li>
        <li>
          <strong>Dashboard &amp; CRM.</strong> Usamos contatos, negócios, atividades, arquivos importados e
          dados retornados pelas APIs que você configurar para organizar o funil e montar painéis. Fontes
          internas podem usar dados das outras soluções da sua conta.
        </li>
        <li>
          <strong>Catálogo &amp; Estoque e Propostas &amp; PDFs.</strong> Usamos produtos, serviços, preços,
          movimentações, pedidos e dados de clientes e outras partes incluídos em propostas, ordens de
          serviço, contratos e recibos.
        </li>
        <li>
          <strong>Projetos &amp; Tarefas e Agenda &amp; Compromissos.</strong> Usamos descrições, prazos,
          listas de tarefas, registros de horas e dados de compromissos. A agenda reúne informações da
          mesma conta, como retornos, entregas, fechamentos, vencimentos e validades do Cofre.
        </li>
        <li>
          <strong>Cofre &amp; Garantias.</strong> Guardamos os documentos, imagens, datas de validade e
          vínculos que você cadastrar. Para facilitar a busca, o Cofre pode extrair e guardar o texto
          dos arquivos com leitura local, inclusive por reconhecimento de caracteres (OCR).
        </li>
        <li>
          <strong>Caderno &amp; Conhecimento.</strong> Guardamos suas notas, etiquetas, links e vínculos
          para organizar e pesquisar o conteúdo. Um roteiro do Caderno pode ser usado na composição
          de mensagens. Seu conteúdo segue para o destinatário se você decidir enviar a mensagem.
        </li>
      </ul>
      <p>
        Tratamos dados necessários para prestar o serviço e executar as operações que você solicitar. Usamos
        legítimo interesse para segurança, prevenção de abuso e diagnóstico, quando aplicável e respeitando
        seus direitos. Também tratamos dados para cumprir obrigações legais ou exercer direitos. Quando um
        tratamento depender de consentimento, pediremos sua autorização separadamente.
      </p>

      <h2>3. Como os dados circulam</h2>
      <p>
        As soluções da sua conta podem trocar os dados necessários a cada recurso. Por exemplo, um pedido
        pode gerar uma receita no Meu Orçamento, um contato da Mensageria pode ser salvo no CRM e o prazo de
        uma tarefa pode aparecer na Agenda.
      </p>
      <ul>
        <li>
          <strong>Hospedagem e e-mail.</strong> A infraestrutura é {LEGAL.hostingProvider}. O serviço de envio
          de e-mails, {LEGAL.emailProvider}, recebe os endereços e o conteúdo necessários para entregar
          mensagens da conta e avisos por e-mail.
        </li>
        <li>
          <strong>WhatsApp.</strong> Ao conectar a Mensageria, o Hub troca com o WhatsApp os dados para vincular
          a conta, sincronizar conversas e entregar mensagens aos destinatários escolhidos. Isso pode incluir
          documentos ou confirmações enviados a partir de outras soluções.
        </li>
        <li>
          <strong>APIs do CRM.</strong> Quando uma fonte externa é consultada, o serviço escolhido recebe a
          requisição e as credenciais configuradas, quando exigidas. O Hub pode guardar os dados retornados
          para usar em painéis ou importações.
        </li>
        <li>
          <strong>Avisos e compartilhamento.</strong> Quando habilitados, avisos podem passar pelo serviço de
          notificações do navegador ou pelo webhook que você definir. Quem receber um arquivo ou link de
          compartilhamento pode acessar as informações liberadas nele.
        </li>
      </ul>
      <p>
        Consultamos os índices públicos do Banco Central sem enviar dados da sua conta. Os motores fiscais, a
        leitura de documentos e o Tire sua dúvida rodam no próprio Hub. Não vendemos dados pessoais nem os usamos
        para publicidade. Podemos fornecer informações a autoridades quando houver obrigação legal ou ordem válida.
      </p>

      <h2>4. Cookies e armazenamento no navegador</h2>
      <p>
        O cookie de sessão mantém você conectado. O navegador também pode guardar preferências de interface
        e arquivos do aplicativo, incluindo cópias de alguns dados já abertos na sua conta, para ajudar
        quando a conexão estiver lenta ou indisponível. Ao encerrar a sessão, o Hub solicita a limpeza
        dessas cópias da conta no dispositivo. O Hub não usa cookies de publicidade nem ferramentas de
        rastreamento publicitário.
      </p>

      <h2>5. Por quanto tempo guardamos os dados</h2>
      <ul>
        <li>
          Os dados da conta e os registros das soluções são mantidos para prestar o serviço até que sejam
          excluídos ou a conta seja encerrada, respeitadas as obrigações legais.
        </li>
        <li>
          O prazo padrão dos registros de segurança é de 180 dias. O histórico de e-mails enviados é
          removido após 30 dias, e os registros de erros, após 90 dias sem nova ocorrência.
        </li>
        <li>Sessões expiradas e links de acesso usados ou vencidos são removidos na rotina de limpeza.</li>
        <li>
          O histórico do Tire sua dúvida é removido 30 dias depois da última mensagem. Você pode apagá-lo
          antes ou desligar o histórico nas <Link to="/ajustes/preferencias#privacidade">Preferências do Meu Orçamento</Link>.
        </li>
        <li>
          A rotina da Mensageria remove do Hub mensagens e mídias com mais de sete dias. As mídias de cada
          conta ocupam no máximo 300 MB: passando disso, as mais antigas saem antes. Conversas fixadas
          ou com informações de atendimento ou vínculos podem continuar na lista. A cópia do WhatsApp
          segue as regras do próprio WhatsApp. Se você arquivar uma mídia no Cofre, essa cópia continua
          guardada até ser excluída ou a conta ser encerrada.
        </li>
        <li>O Hub processa o XML e o PDF do DANFSe durante a solicitação, sem armazenar os arquivos.</li>
        <li>
          Ao excluir a conta, seus dados vinculados são removidos da base principal. As cópias de segurança
          criptografadas seguem a rotação do ambiente: sete dias para cópias no servidor e, nas cópias
          remotas, quando configuradas, as diárias dos últimos sete dias e as semanais das últimas quatro
          semanas. As mídias da Mensageria não entram nas cópias de segurança.
        </li>
      </ul>

      <h2>6. Como exercer seus direitos</h2>
      <ul>
        <li>Você pode atualizar seus dados de identificação em <Link to="/perfil">Perfil</Link>.</li>
        <li>
          Em <Link to="/ajustes/dados?aba=exportar">Meu Orçamento → Ajustes → Importar e exportar</Link>,
          você pode baixar os registros disponíveis dessa solução. O backup inclui alguns dados da conta
          e não reúne todos os dados das outras soluções.
        </li>
        <li>
          Use <Link to="/seguranca">Segurança → Excluir conta</Link> para encerrar sua conta. Arquivos e
          mensagens já compartilhados podem continuar com quem os recebeu.
        </li>
      </ul>
      <p>
        Escreva para <Contact /> para pedir confirmação do tratamento, acesso, correção ou informações sobre
        compartilhamento e, quando cabível, portabilidade, eliminação, bloqueio ou anonimização. Você também
        pode se opor a tratamento em desconformidade com a LGPD ou revogar um consentimento que tenha dado.
        Atendemos nos prazos legais e podemos confirmar sua identidade para proteger seus dados. Você também pode
        <a href="https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados/direito-dos-titulares"> recorrer à ANPD</a>.
      </p>

      <h2>7. Segurança, idade e alterações</h2>
      <p>
        Usamos HTTPS, guardamos senhas como resumos criptográficos e oferecemos verificação em duas etapas.
        Você pode revisar e encerrar sessões em <Link to="/seguranca">Segurança</Link>. A comunicação de
        incidentes aos titulares e à ANPD segue os critérios e prazos legais.
      </p>
      <p>
        O Hub é destinado a maiores de 18 anos. Mudanças relevantes serão comunicadas por e-mail ou no
        aplicativo antes de entrarem em vigor. A versão e a data estão no topo desta página.
      </p>
    </LegalPage>
  );
}

export function Terms() {
  return (
    <LegalPage title="Termos de uso">
      <p>
        Estes termos regem o uso do {LEGAL.serviceName}, oferecido por <Controller />. Ao criar uma conta, você
        aceita estes termos e declara que leu a <Link to="/privacidade">Política de privacidade</Link>.
      </p>

      <h2>1. O que o Hub oferece</h2>
      <p>
        O Hub reúne Meu Orçamento, Mensageria, Dashboard &amp; CRM, Catálogo &amp; Estoque, Propostas &amp; PDFs,
        Projetos &amp; Tarefas, Agenda &amp; Compromissos, Cofre &amp; Garantias e Caderno &amp; Conhecimento.
        Você pode organizar suas finanças e atividades
        pessoais ou comerciais, com integrações que usam dados da sua própria conta.
      </p>
      <p>
        A administração pode liberar o acesso a cadastros, definir limites de armazenamento e restringir
        soluções ou recursos para proteger e manter o serviço.
      </p>

      <h2>2. Conta e uso permitido</h2>
      <ul>
        <li>Para criar uma conta, você precisa ter pelo menos 18 anos e informar um e-mail válido que possa usar.</li>
        <li>
          Proteja sua senha, seus códigos de acesso e seus links privados. Se suspeitar de uso indevido,
          avise-nos pelo <Contact />.
        </li>
        <li>
          Use dados e documentos de clientes, contatos e outras pessoas com uma base legal e respeite os
          direitos dessas pessoas. Se agir em nome de uma empresa, tenha poderes para isso.
        </li>
        <li>
          São proibidos o acesso indevido a contas, a coleta não autorizada de dados, o envio de spam,
          a automação abusiva e o uso para atividades ilegais. O acesso pode ser restringido em caso de
          abuso ou ameaça à segurança, respeitados os direitos previstos em lei.
        </li>
      </ul>

      <h2>3. WhatsApp, APIs e compartilhamento</h2>
      <p>
        A Mensageria se conecta ao WhatsApp por QR Code como aparelho vinculado, por uma integração não oficial.
        A conexão depende do WhatsApp e pode ser interrompida ou bloqueada. Vincule somente contas que você
        esteja autorizado a usar e respeite as regras do WhatsApp.
      </p>
      <p>
        No Dashboard &amp; CRM, use credenciais e fontes de API às quais você tem direito de acesso.
        Ao enviar um documento, configurar um webhook ou compartilhar um link, revise o conteúdo e o
        destino. Os serviços externos têm regras próprias e podem limitar ou interromper o acesso.
      </p>

      <h2>4. Análises, simulações e documentos</h2>
      <ul>
        <li>
          Análises, projeções e simulações são informativas e dependem dos dados informados. Elas não
          substituem orientação financeira, contábil, fiscal ou jurídica quando necessária.
        </li>
        <li>
          A Reforma Tributária usa os motores da Receita Federal e a base fiscal instalada. Confira a
          vigência, o enquadramento e as alíquotas antes de usar uma simulação. O DANFSe é o PDF de uma
          NFS-e já emitida. A emissão da nota ocorre no sistema emissor.
        </li>
        <li>
          Propostas, ordens de serviço, contratos e recibos em PDF são gerados com os dados que você informar.
          Revise o conteúdo e providencie as assinaturas ou outras formalidades necessárias. Lançamentos no
          Meu Orçamento registram operações para controle e não movimentam dinheiro.
        </li>
      </ul>

      <h2>5. Seus registros, disponibilidade e encerramento</h2>
      <p>
        Você mantém os direitos sobre o conteúdo que cadastrar, respeitados os direitos de terceiros.
        O Hub trata essas informações conforme a Política de Privacidade. As opções de exportação dependem
        da solução e do recurso.
      </p>
      <p>
        O serviço pode ficar indisponível por manutenção ou falhas, inclusive de serviços externos.
        Aplicam-se as responsabilidades e os direitos previstos em lei, inclusive no Código de Defesa
        do Consumidor quando aplicável.
      </p>
      <p>
        Você pode encerrar sua conta em <Link to="/seguranca">Segurança → Excluir conta</Link>. Se o serviço
        for descontinuado, avisaremos com pelo menos 30 dias de antecedência para permitir a exportação
        dos dados disponíveis.
      </p>

      <h2>6. Mudanças, lei aplicável e contato</h2>
      <p>
        Mudanças relevantes serão comunicadas por e-mail ou no aplicativo antes de entrarem em vigor.
        Estes termos seguem a lei brasileira. Fica eleito o foro de {LEGAL.forumCity}, respeitado o direito
        do consumidor de recorrer ao foro de seu domicílio. Para falar conosco, escreva para <Contact />.
      </p>
    </LegalPage>
  );
}
