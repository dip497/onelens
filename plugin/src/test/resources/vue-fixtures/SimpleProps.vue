<script setup>
const props = defineProps({
  title: String,
  count: { type: Number, default: 0 },
  active: { type: Boolean, required: true }
})

const emit = defineEmits(['update', 'close'])

defineExpose({
  reset: () => {}
})
</script>

<template>
  <div>{{ title }} ({{ count }})</div>
</template>
