const state = () => ({
  profile: null,
  token: ''
})

const getters = {
  isLoggedIn: s => !!s.token
}

const mutations = {
  SET_PROFILE(s, v) {
    s.profile = v
  },
  SET_TOKEN(s, v) {
    s.token = v
  }
}

const actions = {
  async fetchProfile({ commit }) {
    const { data } = await this.$axios.get('/api/user/profile')
    commit('SET_PROFILE', data)
  }
}

export default {
  namespaced: true,
  state,
  getters,
  mutations,
  actions
}
