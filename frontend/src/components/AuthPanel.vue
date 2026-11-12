<script setup>
import { ref } from 'vue'
import { api } from '../api'

const emit = defineEmits(['done', 'close'])
const register = ref(false)
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  busy.value = true
  error.value = ''
  try {
    await api(`/api/auth/${register.value ? 'register' : 'login'}`, {
      method: 'POST', body: { username: username.value, password: password.value },
    })
    password.value = ''
    emit('done')
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="account-panel auth-panel" aria-label="账号登录">
    <div class="section-heading">
      <h2>{{ register ? '创建账号' : '登录 Sight' }}</h2>
      <button type="button" class="text-button" @click="emit('close')">关闭</button>
    </div>
    <p class="help">登录后可保存 Agent、对话、订阅和阅读记录。</p>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <form class="auth-form" @submit.prevent="submit">
      <label>用户名<input v-model="username" name="username" autocomplete="username" required minlength="3" maxlength="32" pattern="[a-zA-Z0-9_]+" placeholder="英文字母、数字或下划线" /></label>
      <label>密码<input v-model="password" name="password" type="password" :autocomplete="register ? 'new-password' : 'current-password'" required :minlength="register ? 8 : 1" maxlength="128" placeholder="注册密码至少 8 位" /></label>
      <button class="primary" type="submit" :disabled="busy">{{ busy ? '处理中…' : register ? '注册并登录' : '登录' }}</button>
      <button class="text-button" type="button" :disabled="busy" @click="register = !register; error = ''">{{ register ? '已有账号，去登录' : '没有账号，去注册' }}</button>
    </form>
  </section>
</template>
