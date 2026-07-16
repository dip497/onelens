<script setup>
import { useCounter } from './useCounter'
import { useUserStore } from './userStore'

const { count, increment } = useCounter()
const userStore = useUserStore()
userStore.fetchProfile()
</script>

<template>
  <button @click="increment">{{ count }} - {{ userStore.name }}</button>
</template>
