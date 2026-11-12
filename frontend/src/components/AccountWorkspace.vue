<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({ view: String })
const emit = defineEmits(['open-digest', 'profiles-changed'])
const profiles = ref([])
const conversations = ref([])
const records = ref([])
const conversation = ref(null)
const messages = ref([])
const selectedAgent = ref('')
const content = ref('')
const busy = ref(false)
const error = ref('')
const status = ref('')
const editingId = ref('')
const form = ref({ name: '', provider: 'deepseek', model: 'deepseek-flash', system_prompt: '你是中文资讯助手，回答简洁、准确。' })
const selectedProfile = computed(() => profiles.value.find((profile) => profile.id === selectedAgent.value))

async function perform(action) {
  error.value = ''
  status.value = ''
  busy.value = true
  try { await action() } catch (err) { error.value = err.message } finally { busy.value = false }
}

async function refresh() {
  const [agents, chats, history] = await Promise.all([api('/api/agents'), api('/api/conversations'), api('/api/digests')])
  profiles.value = agents.agents
  conversations.value = chats.conversations
  records.value = history.digests
  if (!profiles.value.some((profile) => profile.id === selectedAgent.value)) selectedAgent.value = profiles.value[0]?.id || ''
}

function resetForm() {
  editingId.value = ''
  form.value = { name: '', provider: 'deepseek', model: 'deepseek-flash', system_prompt: '你是中文资讯助手，回答简洁、准确。' }
}

function edit(profile) {
  editingId.value = profile.id
  form.value = { ...profile }
}

async function saveAgent() {
  await perform(async () => {
    await api(editingId.value ? `/api/agents/${editingId.value}` : '/api/agents', { method: editingId.value ? 'PUT' : 'POST', body: form.value })
    await refresh()
    resetForm()
    status.value = 'Agent 已保存，新对话会使用这份配置。'
    emit('profiles-changed')
  })
}

async function removeAgent(profile) {
  if (!window.confirm(`删除 Agent「${profile.name}」？已有对话会保留。`)) return
  await perform(async () => {
    await api(`/api/agents/${profile.id}`, { method: 'DELETE' })
    if (editingId.value === profile.id) resetForm()
    await refresh()
    emit('profiles-changed')
  })
}

async function newConversation() {
  await perform(async () => {
    const data = await api('/api/conversations', { method: 'POST', body: { agent_id: selectedAgent.value } })
    conversation.value = data.conversation
    messages.value = []
    content.value = ''
    await refresh()
  })
}

async function openConversation(id) {
  await perform(async () => {
    const data = await api(`/api/conversations/${id}`)
    conversation.value = data.conversation
    messages.value = data.messages
    content.value = ''
  })
}

async function send() {
  if (!content.value.trim() || !conversation.value) return
  await perform(async () => {
    const data = await api(`/api/conversations/${conversation.value.id}/messages`, {
      method: 'POST', body: { content: content.value }, signal: AbortSignal.timeout(120000),
    })
    messages.value.push(...data.messages)
    conversation.value = data.conversation
    content.value = ''
    await refresh()
  })
}

async function removeConversation(id) {
  if (!window.confirm('删除这段对话及全部消息？')) return
  await perform(async () => {
    await api(`/api/conversations/${id}`, { method: 'DELETE' })
    if (conversation.value?.id === id) { conversation.value = null; messages.value = [] }
    await refresh()
  })
}

async function openDigest(id) {
  await perform(async () => emit('open-digest', await api(`/api/digests/${id}`)))
}

async function removeDigest(id) {
  if (!window.confirm('删除这份阅读记录？')) return
  await perform(async () => { await api(`/api/digests/${id}`, { method: 'DELETE' }); await refresh() })
}

function time(value) { return new Date(value).toLocaleString('zh-CN', { hour12: false }) }
onMounted(() => perform(refresh))
watch(() => props.view, () => { error.value = ''; status.value = '' })
</script>

<template>
  <section class="personal-workspace">
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="status" class="notice" role="status">{{ status }}</p>
    <p v-if="busy" class="help" role="status">正在处理，请稍候…</p>
    <template v-if="view === 'agents'">
      <div class="account-layout">
        <section class="account-panel">
          <h2>我的 Agent</h2>
          <p class="help">模型密钥使用后端配置；修改 Agent 不影响已有对话。</p>
          <p v-if="!profiles.length" class="help">还没有 Agent，请先创建一个。</p>
          <div v-for="profile in profiles" :key="profile.id" class="record-row">
            <div><strong>{{ profile.name }}</strong><small>{{ profile.provider }} / {{ profile.model }}</small></div>
            <div class="row-actions"><button class="text-button" :disabled="busy" @click="edit(profile)">编辑</button><button class="text-button danger" :disabled="busy" @click="removeAgent(profile)">删除</button></div>
          </div>
        </section>
        <section class="account-panel">
          <h2>{{ editingId ? '编辑 Agent' : '创建 Agent' }}</h2>
          <form class="stacked-form" @submit.prevent="saveAgent">
            <label>Agent 名称<input v-model="form.name" required maxlength="60" /></label>
            <label>模型服务<select v-model="form.provider" @change="form.model = form.provider === 'deepseek' ? 'deepseek-flash' : 'qwen-plus'"><option value="deepseek">DeepSeek 官方</option><option value="dashscope">阿里云百炼</option></select></label>
            <label>模型名称<input v-model="form.model" required maxlength="100" /></label>
            <label>系统提示词<textarea v-model="form.system_prompt" rows="5" required maxlength="4000"></textarea></label>
            <div class="form-actions"><button class="primary" :disabled="busy" type="submit">保存 Agent</button><button v-if="editingId" class="secondary" type="button" :disabled="busy" @click="resetForm">取消编辑</button></div>
          </form>
        </section>
      </div>
    </template>
    <template v-else-if="view === 'chats'">
      <div class="account-layout chat-layout">
        <aside class="account-panel">
          <h2>对话记录</h2>
          <label class="field-label" for="chat-agent">新对话使用的 Agent</label>
          <select id="chat-agent" v-model="selectedAgent" class="full-width" :disabled="busy"><option v-for="profile in profiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></select>
          <button class="primary new-chat" :disabled="busy || !selectedProfile" @click="newConversation">新建对话</button>
          <p class="help">最近 50 段对话，按更新时间排列。</p>
          <div v-for="chat in conversations" :key="chat.id" class="record-row" :class="{ active: conversation?.id === chat.id }">
            <button class="record-link" :disabled="busy" @click="openConversation(chat.id)">{{ chat.title }}<small>{{ chat.agent_name }}</small></button>
            <button class="text-button danger" :disabled="busy" :aria-label="`删除对话 ${chat.title}`" @click="removeConversation(chat.id)">删除</button>
          </div>
        </aside>
        <section class="account-panel chat-panel">
          <template v-if="conversation">
            <h2>{{ conversation.title }}</h2><p class="help">{{ conversation.agent_name }} · {{ conversation.model }}</p>
            <div class="chat-log" role="log" aria-label="对话消息" aria-live="polite">
              <p v-if="!messages.length" class="help">开始第一条消息吧，成功的对话会自动保存。</p>
              <article v-for="message in messages" :key="message.id" class="chat-message" :class="message.role"><small>{{ message.role === 'user' ? '你' : conversation.agent_name }}</small><p>{{ message.content }}</p></article>
            </div>
            <form class="stacked-form" @submit.prevent="send">
              <label>消息<textarea v-model="content" rows="3" maxlength="6000" required placeholder="输入问题…" :disabled="busy"></textarea></label>
              <button class="primary" type="submit" :disabled="busy || !content.trim()">{{ busy ? '正在回复…' : '发送消息' }}</button>
            </form>
          </template>
          <div v-else class="empty-result">选择历史对话，或先创建一段新对话。</div>
        </section>
      </div>
    </template>
    <section v-else-if="view === 'history'" class="account-panel">
      <h2>阅读记录</h2><p class="help">最近 50 份清单，可重新打开并导出。</p>
      <div v-if="!records.length" class="empty-result">登录后生成的清单会保存在这里。</div>
      <div v-for="record in records" :key="record.id" class="record-row">
        <button class="record-link" :disabled="busy" @click="openDigest(record.id)">{{ record.demo ? '示例清单 · ' : '' }}{{ record.overview }}<small>{{ time(record.created_at) }} · {{ record.count }} 条</small></button>
        <button class="text-button danger" :disabled="busy" @click="removeDigest(record.id)">删除</button>
      </div>
    </section>
  </section>
</template>
