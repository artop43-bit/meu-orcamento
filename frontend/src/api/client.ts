export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`, { credentials: "include" });
  if (!response.ok) {
    throw new ApiError(response.status, `Erro ${response.status} em ${path}`);
  }
  return response.json() as Promise<T>;
}
