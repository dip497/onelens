// Fixture: a Vitest vi.mock() factory that redefines a store with the SAME
// Pinia id ("user") as the real userStore.js, but with fewer actions.
//
// Before the identity-model fix, this mock collided with the real store via
// MERGE (n:Store {id: "user"}) and last-write-wins overwrote the real store's
// fetchProfile action. After the fix, the mock gets its own fqn
// ("__tests__/mockStore.test.js::useUserStore") and coexists as a separate
// node tagged isTest=true — same model as Java's Bar vs BarTest.
import { defineStore } from 'pinia'

const useUserStore = defineStore('user', {
  state: () => ({ name: '' }),
  actions: {
    stubAction: () => {},
  },
})

export { useUserStore }
