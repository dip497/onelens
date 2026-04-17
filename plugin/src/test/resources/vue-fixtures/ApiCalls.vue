<script setup>
import axios from 'axios'

const moduleName = 'tickets'

async function search(qual) {
  return axios.post(`/${moduleName}/search/byqual`, { qualDetails: qual })
}

async function getById(id) {
  return axios.get(`/tickets/${id}`)
}
</script>

<template>
  <div>Stub</div>
</template>
