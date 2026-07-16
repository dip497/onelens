import { defineStore } from 'pinia'

export const useUserStore = defineStore('user', {
  state: () => ({ name: '', id: null }),
  getters: {
    isLoggedIn: (state) => state.id !== null
  },
  actions: {
    async fetchProfile() {
      const data = await fetch('/api/me').then(r => r.json())
      this.name = data.name
      this.id = data.id
    }
  }
})
