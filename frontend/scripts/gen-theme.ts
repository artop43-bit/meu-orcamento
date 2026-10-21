// Gera src/theme.css a partir de src/theme/tokens.ts (npm run theme).
import { writeFileSync } from "node:fs";

import { themeCss } from "../src/theme/css.ts";

writeFileSync(new URL("../src/theme.css", import.meta.url), themeCss());
console.log("src/theme.css atualizado");
