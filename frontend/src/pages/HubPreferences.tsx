import { MessageSquarePlus } from "lucide-react";

import { AppearanceSection } from "../components/AppearanceSettings";
import { EmailNoticesSection } from "../components/NotificationBlocks";
import { openFeedback } from "../components/power";
import { WebhookSettings } from "../components/WebhookSettings";
import { Button, PageHeader } from "../components/ui";

/** Preferências da conta no Hub: aparência global, avisos da conta e feedback. */
export default function HubPreferences() {
  return (
    <>
      <PageHeader title="Preferências" subtitle="Aparência, avisos da conta e sugestões." />
      <div className="layout-main-side">
        <div className="stack" style={{ gap: 20 }}>
          <AppearanceSection />
          <EmailNoticesSection scope="account" />
          <WebhookSettings scope="account" />
        </div>
        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <h2>Feedback</h2>
            <p className="muted" style={{ margin: 0 }}>
              Relate problemas ou envie sugestões diretamente à equipe.
            </p>
            <div>
              <Button type="button" variant="secondary" onClick={openFeedback}>
                <MessageSquarePlus size={16} /> Enviar feedback
              </Button>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
