import { useEffect, useState } from "react";

import { contactInitials } from "../../lib/messaging";

/** Foto de perfil do contato com volta automática para as iniciais se a foto faltar ou falhar. */
export function ChatAvatar({ name, avatarUrl }: { name: string; avatarUrl?: string | null }) {
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    setBroken(false);
  }, [avatarUrl]);

  if (avatarUrl && !broken) {
    return (
      <span className="wa-avatar wa-avatar--photo" aria-hidden>
        <img
          src={avatarUrl}
          alt=""
          className="wa-avatar__img"
          loading="lazy"
          onError={() => setBroken(true)}
        />
      </span>
    );
  }

  return (
    <span className="wa-avatar" aria-hidden>
      {contactInitials(name)}
    </span>
  );
}
