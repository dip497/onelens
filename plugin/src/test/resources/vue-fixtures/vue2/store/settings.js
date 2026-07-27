// Lives under store/ but is NOT a Vuex module — only one recognised section.
// VuexStoreCollector must reject it on shape, not accept it on location.
export default {
  state: 'not-a-store'
}
