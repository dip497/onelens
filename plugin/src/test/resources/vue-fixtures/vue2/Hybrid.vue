<template>
  <div>{{ label }}</div>
</template>

<script setup>
// Vue 2.7 backported the compiler macros — a 2.x repo can hold both styles.
const props = defineProps({ label: String })
</script>
