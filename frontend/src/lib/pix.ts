/**
 * Pix "copia e cola" (v1.4): código estático do Banco Central (BR Code, padrão EMV) com a chave
 * da pessoa e o valor. É gerado no aparelho, sem banco nem taxa; o app do banco de quem paga lê
 * o código e confirma nome e valor antes de pagar.
 */

function field(id: string, value: string): string {
  return `${id}${String(value.length).padStart(2, "0")}${value}`;
}

/** Nome e cidade no código: maiúsculas, sem acentos e no tamanho máximo do padrão. */
function clean(text: string, max: number): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^A-Za-z0-9 ]/g, "")
    .trim()
    .toUpperCase()
    .slice(0, max);
}

/** CRC16-CCITT (polinômio 0x1021, início 0xFFFF), exigido no fim do código. */
export function crc16(payload: string): string {
  let crc = 0xffff;
  for (let i = 0; i < payload.length; i++) {
    crc ^= payload.charCodeAt(i) << 8;
    for (let bit = 0; bit < 8; bit++) {
      crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
  }
  return crc.toString(16).toUpperCase().padStart(4, "0");
}

export function pixCode({
  key,
  name,
  city,
  amount,
  message,
}: {
  key: string;
  name: string;
  city: string;
  amount?: number;
  message?: string;
}): string {
  const info = field("00", "br.gov.bcb.pix") + field("01", key) + (message ? field("02", clean(message, 40)) : "");
  const body =
    field("00", "01") +
    field("26", info) +
    field("52", "0000") +
    field("53", "986") +
    (amount && amount > 0 ? field("54", amount.toFixed(2)) : "") +
    field("58", "BR") +
    field("59", clean(name, 25) || "RECEBEDOR") +
    field("60", clean(city, 15) || "BRASIL") +
    field("62", field("05", "***"));
  const withCrc = `${body}6304`;
  return withCrc + crc16(withCrc);
}
