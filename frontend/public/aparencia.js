// Aplica o tema e as preferências de aparência antes da primeira pintura da tela, para o app
// não "piscar" no tema claro ao abrir. Arquivo externo (e não <script> embutido) por causa da
// política de segurança do site, que só permite scripts do próprio domínio.
(function () {
  try {
    var prefs = JSON.parse(localStorage.getItem("preferencias-v1") || "{}");
    var root = document.documentElement;
    if (prefs.theme === "light" || prefs.theme === "dark") root.dataset.theme = prefs.theme;
    if (prefs.accent) root.dataset.accent = prefs.accent;
    root.dataset.style = prefs.style === "glass" ? "glass" : "padrao";
    // Liquid glass mais leve em aparelhos simples (desfoque pesa na GPU).
    var cores = navigator.hardwareConcurrency || 8;
    var memory = navigator.deviceMemory || 8;
    if (cores <= 4 || memory <= 3) root.dataset.lite = "1";
    if (prefs.text) root.dataset.text = prefs.text;
    if (prefs.density) root.dataset.density = prefs.density;
  } catch (e) {
    // Sem armazenamento (navegação privada): segue o tema do sistema.
  }
})();
