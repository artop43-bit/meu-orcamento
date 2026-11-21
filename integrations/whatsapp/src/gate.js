// Limita quantas sessões fazem pareamento/sincronização inicial ao mesmo tempo no processo.

export class Gate {
  constructor (limit) {
    this.limit = Math.max(1, Math.floor(Number(limit) || 1))
    this.active = 0
    this.waiting = []
  }

  /** Espera uma vaga. Devolve uma função que libera a vaga (pode chamar mais de uma vez). */
  acquire () {
    return new Promise((resolve) => {
      const grant = () => {
        this.active += 1
        let released = false
        resolve(() => {
          if (released) return
          released = true
          this.active -= 1
          const next = this.waiting.shift()
          if (next) next()
        })
      }
      if (this.active < this.limit) grant()
      else this.waiting.push(grant)
    })
  }

  get pending () {
    return this.waiting.length
  }
}
