import { useState } from "react";
import { Download } from "lucide-react";

import { errorMessage } from "../api/client";
import { download } from "../api/data";
import { announce } from "../lib/announce";
import { Button } from "./ui";

/** Baixa o PDF gerado no servidor (v1.7.6.1): arquivo de verdade, sem passar pela impressão. */
export function PdfButton({ path, name }: { path: string; name: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <>
      <Button
        type="button"
        loading={busy}
        onClick={async () => {
          setError("");
          setBusy(true);
          try {
            await download(path, name);
            announce("Download iniciado.");
          } catch (err) {
            setError(errorMessage(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Download size={16} aria-hidden /> Baixar PDF
      </Button>
      {error && (
        <span className="tone--error small" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
