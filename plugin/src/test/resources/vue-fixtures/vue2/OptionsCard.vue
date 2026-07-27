<template>
  <div class="card" @click="save">
    <h3>{{ title }}</h3>
    <child-card :count="count" />
  </div>
</template>

<script>
import ChildCard from './ChildCard.vue'
import formMixin from '@/mixins/formMixin'
import tableMixin from '@/mixins/tableMixin'
import { mapState, mapActions } from 'vuex'

export default {
  name: 'UserCard',
  components: { ChildCard },
  mixins: [formMixin, tableMixin],
  props: {
    title: String,
    active: { type: Boolean, required: true },
    count: { type: Number, default: 0 }
  },
  data() {
    return { open: false }
  },
  computed: {
    ...mapState('user', ['profile'])
  },
  methods: {
    ...mapActions('user', ['fetchProfile']),
    save() {
      this.$emit('save', this.title)
      this.$emit('close')
    }
  }
}
</script>
