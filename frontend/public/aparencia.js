// Aplica o tema e as preferências de aparência antes da primeira pintura da tela, para o app
// não "piscar" no tema claro ao abrir. Arquivo externo (e não <script> embutido) por causa da
// política de segurança do site, que só permite scripts do próprio domínio.
(function () {
  try {
    var prefs = JSON.parse(localStorage.getItem("preferencias-v1") || "{}");
    var root = document.documentElement;
    if (prefs.theme === "light" || prefs.theme === "dark") root.dataset.theme = prefs.theme;
    if (prefs.accent) root.dataset.accent = prefs.accent;
    if (prefs.text) root.dataset.text = prefs.text;
    if (prefs.density) root.dataset.density = prefs.density;
  } catch (e) {
    // Sem armazenamento (navegação privada): segue o tema do sistema.
  }
})();
