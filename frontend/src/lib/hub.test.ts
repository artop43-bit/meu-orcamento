import { describe, expect, it } from "vitest";

import {
  activeSolutions,
  areaForPath,
  canSkipSplashByClick,
  computeSplashExitDelay,
  findSolution,
  HUB_AREA,
  HUB_SOLUTIONS,
  isPlainLeftClick,
  isSolutionArea,
  isSolutionBlocked,
  leaveStillApplies,
  navigateDelay,
  shouldBlockSolutionJump,
  SOLUTION_SPLASH_SKIP_GUARD_MS,
  SOLUTION_SPLASH_TIMING,
  SOLUTION_SPLASH_TIMING_REDUCED,
  solutionForPath,
  splashSolutionForAreas,
  splashTiming,
  type HubSolution,
} from "./hub";

describe("catálogo do hub de soluções", () => {
  it("expõe Meu Orçamento e Mensageria como soluções ativas", () => {
    const budget = findSolution("meu-orcamento");
    expect(budget?.status).toBe("active");
    expect(budget?.to).toBe("/orcamento");

    const messaging = findSolution("mensageria");
    expect(messaging?.status).toBe("active");
    expect(messaging?.to).toBe("/mensageria");
    expect(messaging?.integratesWith).toContain("meu-orcamento");

    const crm = findSolution("dashboard-crm");
    expect(crm?.status).toBe("active");
    expect(crm?.name).toBe("Dashboard & CRM");
    expect(crm?.to).toBe("/crm");
    expect(crm?.integratesWith).toContain("mensageria");
    expect(crm?.integratesWith).toContain("meu-orcamento");
  });

  it("retorna apenas soluções ativas com rota definida", () => {
    const active = activeSolutions();
    expect(active.length).toBeGreaterThanOrEqual(2);
    expect(active.every((item) => item.status === "active" && item.to !== null)).toBe(true);
  });

  it("mantém identificadores únicos para suportar futuras integrações", () => {
    const ids = HUB_SOLUTIONS.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("reconhece a solução dona de cada rota sem confundir o Hub com soluções", () => {
    expect(solutionForPath("/")).toBeNull();
    expect(solutionForPath("/perfil")).toBeNull();
    expect(solutionForPath("/configuracoes")).toBeNull();
    expect(solutionForPath("/mensagens")).toBeNull();
    expect(solutionForPath("/mensagens/conversas")).toBeNull();

    expect(solutionForPath("/orcamento")?.id).toBe("meu-orcamento");
    expect(solutionForPath("/orcamento/2026-11")?.id).toBe("meu-orcamento");
    expect(solutionForPath("/divisoes")?.id).toBe("meu-orcamento");
    expect(solutionForPath("/mensageria")?.id).toBe("mensageria");
    expect(solutionForPath("/mensageria/123")?.id).toBe("mensageria");
    expect(solutionForPath("/crm")?.id).toBe("dashboard-crm");
    expect(solutionForPath("/crm/fontes")?.id).toBe("dashboard-crm");
    expect(solutionForPath("/catalogo")?.id).toBe("catalogo");
    expect(solutionForPath("/catalogo/pedidos")?.id).toBe("catalogo");
    expect(solutionForPath("/propostas")?.id).toBe("propostas");
    expect(solutionForPath("/projetos")?.id).toBe("projetos");
    expect(solutionForPath("/agenda")?.id).toBe("agenda");
    expect(solutionForPath("/cofre")?.id).toBe("cofre");
    expect(solutionForPath("/caderno")?.id).toBe("caderno");
  });
});

describe("áreas do app", () => {
  it("separa soluções, Hub e páginas públicas", () => {
    expect(areaForPath("/orcamento")).toBe("meu-orcamento");
    expect(areaForPath("/orcamento/2026-11")).toBe("meu-orcamento");
    expect(areaForPath("/ajustes/categorias")).toBe("meu-orcamento");
    expect(areaForPath("/relatorio/ano/2026")).toBe("meu-orcamento");
    expect(areaForPath("/mensageria")).toBe("mensageria");
    expect(areaForPath("/mensageria/abc")).toBe("mensageria");

    expect(areaForPath("/")).toBe(HUB_AREA);
    expect(areaForPath("/perfil")).toBe(HUB_AREA);
    expect(areaForPath("/configuracoes")).toBe(HUB_AREA);
    expect(areaForPath("/mensagens/conversas/1")).toBe(HUB_AREA);
    expect(areaForPath("/admin")).toBe(HUB_AREA);
    // Endereço desconhecido cai no Hub (a rota "*" leva para o início).
    expect(areaForPath("/nao-existe")).toBe(HUB_AREA);

    for (const path of ["/entrar", "/cadastro", "/esqueci-senha", "/verificar-email", "/redefinir-senha", "/privacidade", "/termos", "/descadastrar", "/nao-fui-eu"]) {
      expect(areaForPath(path)).toBeNull();
    }
  });

  it("endereços antigos da conta sob /ajustes contam como Hub, não como Meu Orçamento", () => {
    expect(areaForPath("/ajustes/perfil")).toBe(HUB_AREA);
    expect(areaForPath("/ajustes/seguranca")).toBe(HUB_AREA);
    expect(areaForPath("/ajustes/app")).toBe(HUB_AREA);
    expect(areaForPath("/ajustes/notas")).toBe(HUB_AREA);
    expect(areaForPath("/ajustes/solicitacoes")).toBe(HUB_AREA);
    expect(areaForPath("/ajustes/solicitacoes/123")).toBe(HUB_AREA);
    // Prefixo parecido não engana: /ajustes/preferencias é do Meu Orçamento.
    expect(areaForPath("/ajustes/preferencias")).toBe("meu-orcamento");
    expect(areaForPath("/ajustes")).toBe("meu-orcamento");
  });

  it("reconhece só soluções ativas como área de solução", () => {
    expect(isSolutionArea("meu-orcamento")).toBe(true);
    expect(isSolutionArea("mensageria")).toBe(true);
    expect(isSolutionArea(HUB_AREA)).toBe(false);
    expect(isSolutionArea(null)).toBe(false);
    expect(isSolutionArea("desconhecida")).toBe(false);
  });

  it("barra o salto direto entre soluções diferentes, e só ele", () => {
    expect(shouldBlockSolutionJump("meu-orcamento", "mensageria")).toBe(true);
    expect(shouldBlockSolutionJump("mensageria", "meu-orcamento")).toBe(true);

    // Mesma solução, vindo do Hub, de página pública ou sem área anterior (endereço digitado).
    expect(shouldBlockSolutionJump("meu-orcamento", "meu-orcamento")).toBe(false);
    expect(shouldBlockSolutionJump(HUB_AREA, "mensageria")).toBe(false);
    expect(shouldBlockSolutionJump(null, "mensageria")).toBe(false);
    // Indo para o Hub ou para uma página pública, nunca barra.
    expect(shouldBlockSolutionJump("mensageria", HUB_AREA)).toBe(false);
    expect(shouldBlockSolutionJump("mensageria", null)).toBe(false);
  });

  it("solução → telas do Hub → outra solução é permitido", () => {
    const visits = ["/orcamento", "/perfil", "/configuracoes", "/mensagens", "/mensageria"].map((path) => areaForPath(path));
    for (let i = 1; i < visits.length; i++) {
      expect(shouldBlockSolutionJump(visits[i - 1] ?? null, visits[i] ?? null)).toBe(false);
    }
    expect(shouldBlockSolutionJump(areaForPath("/orcamento"), areaForPath("/mensageria/abc"))).toBe(true);
  });

  it("toca a animação de entrada só ao chegar numa solução vindo do Hub", () => {
    expect(splashSolutionForAreas(HUB_AREA, "meu-orcamento")?.id).toBe("meu-orcamento");
    expect(splashSolutionForAreas(HUB_AREA, "mensageria")?.name).toBe("Mensageria");

    expect(splashSolutionForAreas(null, "meu-orcamento")).toBeNull(); // abriu direto (sem área anterior)
    expect(splashSolutionForAreas("mensageria", "meu-orcamento")).toBeNull(); // salto barrado antes
    expect(splashSolutionForAreas("meu-orcamento", "meu-orcamento")).toBeNull();
    expect(splashSolutionForAreas(HUB_AREA, HUB_AREA)).toBeNull();
    expect(splashSolutionForAreas("meu-orcamento", HUB_AREA)).toBeNull();
  });

  it("aceita um catálogo próprio (soluções em preparação não contam)", () => {
    const catalog: HubSolution[] = [
      { ...HUB_SOLUTIONS[0]!, id: "a", routePrefixes: ["/a"] },
      { ...HUB_SOLUTIONS[0]!, id: "b", routePrefixes: ["/b"], status: "soon", to: null },
    ];
    expect(areaForPath("/a/1", catalog)).toBe("a");
    expect(areaForPath("/b", catalog)).toBe(HUB_AREA);
    expect(shouldBlockSolutionJump("a", "b", catalog)).toBe(false);
  });
});

describe("tempos da transição entre soluções", () => {
  const t = SOLUTION_SPLASH_TIMING;

  it("mantém os tempos combinados", () => {
    expect(t.navigateMinMs).toBeGreaterThanOrEqual(450);
    expect(t.navigateMinMs).toBeLessThanOrEqual(600);
    expect(t.navigateMaxMs).toBeLessThanOrEqual(1500);
    expect(t.visibleMinMs).toBeGreaterThanOrEqual(700);
    expect(t.visibleMaxMs).toBeLessThanOrEqual(2500);
    expect(t.visibleMinMs).toBeGreaterThan(t.navigateMinMs);
    expect(splashTiming(false)).toBe(SOLUTION_SPLASH_TIMING);
    expect(splashTiming(true)).toBe(SOLUTION_SPLASH_TIMING_REDUCED);
    expect(SOLUTION_SPLASH_TIMING_REDUCED.visibleMinMs).toBeLessThan(t.visibleMinMs);
    expect(SOLUTION_SPLASH_TIMING_REDUCED.contentMs).toBe(0);
  });

  it("troca de tela depois do mínimo e do código pronto, o que vier por último, até o limite", () => {
    expect(navigateDelay(0, t)).toBe(t.navigateMinMs); // código já baixado: espera o mínimo
    expect(navigateDelay(100, t)).toBe(t.navigateMinMs);
    expect(navigateDelay(900, t)).toBe(900); // código chegou depois do mínimo: troca na hora
    expect(navigateDelay(5000, t)).toBe(t.navigateMaxMs); // nunca passa do limite
    expect(navigateDelay(null, t)).toBe(t.navigateMaxMs); // ainda sem código: só no limite
    // "Reduzir movimento": troca assim que o código chega.
    expect(navigateDelay(0, SOLUTION_SPLASH_TIMING_REDUCED)).toBe(0);
  });

  it("a animação sai só depois do tempo mínimo visível e nunca passa do limite", () => {
    expect(computeSplashExitDelay(0, t)).toBe(t.visibleMinMs);
    expect(computeSplashExitDelay(500, t)).toBe(t.visibleMinMs - 500);
    expect(computeSplashExitDelay(t.visibleMinMs, t)).toBe(0);
    expect(computeSplashExitDelay(1800, t)).toBe(0); // tela demorou: sai na hora
    expect(computeSplashExitDelay(9999, t)).toBe(0);
    expect(computeSplashExitDelay(-50, t)).toBe(t.visibleMinMs + 50);
    // Limite menor que o mínimo (configuração estranha): o limite vence.
    expect(computeSplashExitDelay(0, { ...t, visibleMinMs: 3000, visibleMaxMs: 2500 })).toBe(2500);
  });

  it("só o clique simples abre com a animação; com teclas modificadoras o navegador decide", () => {
    const click = { button: 0, metaKey: false, altKey: false, ctrlKey: false, shiftKey: false, defaultPrevented: false };
    expect(isPlainLeftClick(click)).toBe(true);
    expect(isPlainLeftClick({ ...click, button: 1 })).toBe(false); // botão do meio: nova aba
    expect(isPlainLeftClick({ ...click, ctrlKey: true })).toBe(false);
    expect(isPlainLeftClick({ ...click, metaKey: true })).toBe(false);
    expect(isPlainLeftClick({ ...click, shiftKey: true })).toBe(false);
    expect(isPlainLeftClick({ ...click, altKey: true })).toBe(false);
    expect(isPlainLeftClick({ ...click, defaultPrevented: true })).toBe(false);
  });

  it("clique na animação pula a entrada, mas não o segundo clique de um duplo clique no cartão", () => {
    const g = SOLUTION_SPLASH_SKIP_GUARD_MS;
    expect(g).toBeLessThan(t.navigateMinMs); // dá para pular antes de a tela trocar
    expect(canSkipSplashByClick(g, 1)).toBe(true);
    expect(canSkipSplashByClick(1200, 1)).toBe(true);
    expect(canSkipSplashByClick(1200, 0)).toBe(true); // clique sem contagem (teclado, leitor de tela)
    expect(canSkipSplashByClick(g - 1, 1)).toBe(false); // logo depois de aparecer
    expect(canSkipSplashByClick(40, 2)).toBe(false); // segundo clique do duplo clique
    expect(canSkipSplashByClick(1200, 2)).toBe(false);
  });

  it("'Sair' só volta ao Hub se a pessoa continua na mesma solução depois do esmaecimento", () => {
    expect(leaveStillApplies("/mensageria", "/mensageria")).toBe(true);
    // Troca de conversa ou de aba dentro da solução não cancela a saída.
    expect(leaveStillApplies("/mensageria/abc", "/mensageria")).toBe(true);
    expect(leaveStillApplies("/orcamento/2026-05", "/cartoes")).toBe(true);
    // Já foi para outra área (voltar do navegador, link): não puxa de volta para o Hub.
    expect(leaveStillApplies("/mensageria", "/")).toBe(false);
    expect(leaveStillApplies("/orcamento", "/perfil")).toBe(false);
    expect(leaveStillApplies("/orcamento", "/mensageria")).toBe(false);
    expect(leaveStillApplies("/orcamento", "/entrar")).toBe(false);
    // Fora de uma solução não há saída a fazer.
    expect(leaveStillApplies("/perfil", "/perfil")).toBe(false);
  });

  it("identifica soluções bloqueadas pelo administrador", () => {
    expect(isSolutionBlocked("mensageria", undefined)).toBe(false);
    expect(isSolutionBlocked("mensageria", [])).toBe(false);
    expect(isSolutionBlocked("mensageria", ["mensageria", "feature:external_api"])).toBe(true);
    expect(isSolutionBlocked("dashboard-crm", ["mensageria"])).toBe(false);
  });
});
