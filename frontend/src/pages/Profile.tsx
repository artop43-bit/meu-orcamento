import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Briefcase, CalendarDays, Camera, ImagePlus, Mail, MapPin, Pencil } from "lucide-react";

import { errorMessage } from "../api/client";
import { profileApi, useProfile, type Profile } from "../api/profile";
import { fileUrl } from "../api/support";
import { ImageEditor } from "../components/imageCrop";
import { Avatar } from "../components/media";
import { Alert, Button, LoadingRegion, PageHeader, Sheet, Skeleton } from "../components/ui";
import { announce } from "../lib/announce";

function personName(profile: Profile): string {
  return profile.display_name || profile.email.split("@")[0]!;
}

function EditProfile({ profile, open, onClose }: { profile: Profile; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    display_name: profile.display_name ?? "",
    profession: profile.profession ?? "",
    city: profile.city ?? "",
    bio: profile.bio ?? "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updated = await profileApi.update(form);
      queryClient.setQueryData(["profile"], updated);
      announce("Perfil atualizado");
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const field = (key: keyof typeof form, label: string, max: number, placeholder: string) => (
    <label>
      {label}
      <input value={form[key]} maxLength={max} placeholder={placeholder} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
    </label>
  );

  return (
    <Sheet open={open} title="Editar perfil" onClose={onClose}>
      <form className="inline-form" onSubmit={submit}>
        <Alert tone="error">{error}</Alert>
        <p className="muted small" style={{ margin: 0 }}>
          Todos os campos são opcionais.
        </p>
        {field("display_name", "Nome de exibição", 60, "Como prefere ser chamado(a)")}
        <div className="grid-2">
          {field("profession", "Profissão", 80, "Ex.: Designer")}
          {field("city", "Cidade", 80, "Ex.: Belo Horizonte")}
        </div>
        <label>
          Sobre você
          <textarea value={form.bio} maxLength={160} rows={2} placeholder="Uma frase curta (até 160 caracteres)" onChange={(e) => setForm({ ...form, bio: e.target.value })} />
        </label>
        <div className="form-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={busy}>
            Salvar
          </Button>
        </div>
      </form>
    </Sheet>
  );
}

/** Perfil pessoal do usuário (nome, foto, banner, e-mail e informações básicas). */
export default function ProfilePage() {
  const profile = useProfile();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [image, setImage] = useState<"avatar" | "banner" | null>(null);

  if (profile.isPending)
    return (
      <LoadingRegion label="Carregando o perfil">
        <Skeleton height={260} />
      </LoadingRegion>
    );
  if (profile.isError) return <Alert tone="error">{errorMessage(profile.error)}</Alert>;
  const data = profile.data;
  const name = personName(data);
  const since = new Date(data.member_since).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });

  async function saveImage(purpose: "avatar" | "banner", blob: Blob, filename: string) {
    const updated = await profileApi.setImage(purpose, blob, filename);
    queryClient.setQueryData(["profile"], updated);
    announce(purpose === "avatar" ? "Foto atualizada" : "Banner atualizado");
  }

  return (
    <>
      <PageHeader title="Perfil" subtitle="Seus dados pessoais e sua foto." />
      <section className="card profile-hero" aria-label="Cartão do perfil">
        <div className="profile-hero__banner" style={data.banner_id ? { backgroundImage: `url(${fileUrl(data.banner_id)})` } : undefined}>
          <button type="button" className="profile-hero__edit-banner" onClick={() => setImage("banner")}>
            <ImagePlus size={16} aria-hidden /> {data.banner_id ? "Trocar banner" : "Adicionar banner"}
          </button>
        </div>
        <div className="profile-hero__body">
          <button type="button" className="profile-hero__avatar" onClick={() => setImage("avatar")} aria-label={data.avatar_id ? "Trocar foto" : "Adicionar foto"}>
            <Avatar fileId={data.avatar_id} name={name} size={104} />
            <span className="profile-hero__camera" aria-hidden>
              <Camera size={16} />
            </span>
          </button>
          <div className="profile-hero__info">
            <h2 className="profile-hero__name">{name}</h2>
            <p className="profile-hero__meta muted">
              <span>
                <Mail size={14} aria-hidden /> {data.email}
              </span>
              {data.profession && (
                <span>
                  <Briefcase size={14} aria-hidden /> {data.profession}
                </span>
              )}
              {data.city && (
                <span>
                  <MapPin size={14} aria-hidden /> {data.city}
                </span>
              )}
              <span>
                <CalendarDays size={14} aria-hidden /> Desde {since}
              </span>
            </p>
            {data.bio && <p className="profile-hero__bio">{data.bio}</p>}
          </div>
          <Button type="button" variant="secondary" className="profile-hero__button" onClick={() => setEditing(true)}>
            <Pencil size={16} /> Editar perfil
          </Button>
        </div>
      </section>

      {editing && <EditProfile profile={data} open={editing} onClose={() => setEditing(false)} />}
      <ImageEditor
        purpose={image ?? "avatar"}
        open={image !== null}
        hasImage={image === "banner" ? Boolean(data.banner_id) : Boolean(data.avatar_id)}
        onClose={() => setImage(null)}
        onSave={(blob, filename) => saveImage(image!, blob, filename)}
        onRemove={async () => {
          const updated = await profileApi.removeImage(image!);
          queryClient.setQueryData(["profile"], updated);
        }}
      />
    </>
  );
}
