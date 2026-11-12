<script setup>
import { onMounted, ref } from 'vue'

const message = ref('正在检查后端连接…')
const loading = ref(false)
const connected = ref(false)

async function checkBackend() {
  loading.value = true
  connected.value = false
  message.value = '正在检查后端连接…'

  try {
    const response = await fetch('/api/health', {
      signal: AbortSignal.timeout(8000),
    })
    if (!response.ok) throw new Error('健康检查失败')
    const result = await response.json()
    if (result.status !== 'ok') throw new Error('后端状态异常')
    message.value = result.message
    connected.value = true
  } catch {
    message.value = '无法连接后端，请确认 Flask 已在 5001 端口启动。'
  } finally {
    loading.value = false
  }
}

onMounted(checkBackend)
</script>

<template>
  <main class="welcome">
    <p class="eyebrow">项目已就绪</p>
    <h1>Sight</h1>
    <p>Vue 3 + Flask + MySQL</p>
    <p role="status" :class="['status', { connected }]">{{ message }}</p>
    <button type="button" :disabled="loading" @click="checkBackend">
      {{ loading ? '检查中…' : '检查后端连接' }}
    </button>
  </main>
</template>
