<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, auth, initAuth } from './api'
import AuthPanel from './components/AuthPanel.vue'
import AccountWorkspace from './components/AccountWorkspace.vue'

const config = ref(null)
const selected = ref([])
const customUrls = ref('')
const limit = ref(10)
const mode = ref('feed')
const loading = ref(false)
const error = ref('')
const result = ref(null)
const search = ref('')
const view = ref('reading')
const showAuth = ref(false)
const profiles = ref([])
const savedSources = ref([])
const selectedAgent = ref('')
const sourceName = ref('')
const sourceUrl = ref('')
const savingSource = ref(false)
const selectedProfile = computed(() => profiles.value.find((profile) => profile.id === selectedAgent.value))
const aiEnabled = computed(() => selectedProfile.value ? config.value?.providers?.[selectedProfile.value.provider] : config.value?.ai_available)
const currentModel = computed(() => selectedProfile.value?.model || config.value?.model)
const allSources = computed(() => [...new Map([...(config.value?.sources || []), ...savedSources.value].map((source) => [source.url, source])).values()])
const visibleArticles = computed(() => {
  const query = search.value.trim().toLowerCase()
  return (result.value?.articles ?? []).filter((article) =>
    `${article.title} ${article.summary} ${article.source}`.toLowerCase().includes(query),
  )
})
const urls = computed(() => [...new Set([
  ...selected.value,
  ...customUrls.value.split('\n').map((url) => url.trim()).filter(Boolean),
])])

async function loadConfig() {
  error.value = ''
  try {
    config.value = await api('/api/rss/config')
    selected.value = config.value.sources.slice(0, 1).map((source) => source.url)
  } catch {
    error.value = '无法连接后端，请确认 Flask 已在 5001 端口启动后重试。'
  }
}

async function generate(demo = false) {
  const requestUserId = auth.user?.id
  error.value = ''
  if (!demo && (!urls.value.length || urls.value.length > 5)) {
    error.value = '请选择或输入 1–5 个订阅地址。'
    return
  }
  loading.value = true
  try {
    const data = await api('/api/digests', {
      method: 'POST',
      body: { urls: demo ? [] : urls.value, limit: limit.value, mode: demo ? 'feed' : mode.value, demo, ...(auth.user && selectedAgent.value ? { agent_id: selectedAgent.value } : {}) },
      signal: AbortSignal.timeout(180000),
    })
    if (auth.user?.id !== requestUserId) return
    result.value = data
    search.value = ''
  } catch (err) {
    error.value = err.name === 'TimeoutError'
      ? '请求超时，请减少信息源或条数后重试。'
      : err instanceof TypeError ? '连接中断，请检查后端是否运行。' : err.message
  } finally {
    loading.value = false
  }
}

function downloadDigest() {
  if (!result.value) return
  const escape = (text) => text.replace(/[\\`*_{}\[\]<>#]/g, '\\$&')
  const content = [
    '# Sight 资讯摘要',
    result.value.demo ? '> 示例数据，非实时新闻。' : '',
    escape(result.value.overview),
    ...result.value.articles.map((article) =>
      `## ${escape(article.title)}\n\n${escape(article.summary)}\n\n来源：${escape(article.source)} · ${article.summary_kind === 'ai' ? 'AI 摘要' : '订阅摘要'}\n\n原文：<${encodeURI(article.url).replace(/>/g, '%3E').replace(/</g, '%3C')}>`,
    ),
    ...result.value.warnings.map((warning) => `提示：${escape(warning)}`),
  ].join('\n\n')
  const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `sight-${result.value.generated_at.slice(0, 10)}.md`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '未提供发布时间'
}

async function loadAgents() {
  const userId = auth.user?.id
  try {
    const data = await api('/api/agents')
    if (auth.user?.id !== userId) return
    profiles.value = data.agents
    if (!profiles.value.some((profile) => profile.id === selectedAgent.value)) selectedAgent.value = profiles.value[0]?.id || ''
  } catch (err) { error.value = err.message }
}

async function saveSource() {
  savingSource.value = true
  error.value = ''
  try {
    await api('/api/sources', { method: 'POST', body: { name: sourceName.value, url: sourceUrl.value } })
    savedSources.value = (await api('/api/sources')).sources
    sourceName.value = ''; sourceUrl.value = ''
  } catch (err) { error.value = err.message } finally { savingSource.value = false }
}

async function removeSource(source) {
  if (!window.confirm(`删除订阅「${source.name}」？`)) return
  try {
    await api(`/api/sources/${source.id}`, { method: 'DELETE' })
    savedSources.value = savedSources.value.filter((row) => row.id !== source.id)
    selected.value = selected.value.filter((url) => url !== source.url)
  } catch (err) { error.value = err.message }
}

async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }) } catch (err) { error.value = err.message }
}

function openDigest(digest) { result.value = digest; search.value = ''; view.value = 'reading' }

watch(() => auth.user?.id, async (userId) => {
  result.value = null; savedSources.value = []; profiles.value = []; selectedAgent.value = ''
  customUrls.value = ''; selected.value = config.value?.sources.slice(0, 1).map((source) => source.url) || []
  sourceName.value = ''; sourceUrl.value = ''; view.value = 'reading'; mode.value = 'feed'
  if (userId) {
    showAuth.value = false
    try { await Promise.all([loadAgents(), api('/api/sources').then((data) => { if (auth.user?.id === userId) savedSources.value = data.sources })]) }
    catch (err) { error.value = err.message }
  }
})
onMounted(async () => {
  await Promise.all([loadConfig(), initAuth().catch((err) => { error.value = err.message })])
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="Sight 首页"><span class="brand-mark">S</span> Sight<span class="brand-note">资讯阅读台</span></a>
      <div class="account-bar"><template v-if="auth.user"><span>{{ auth.user.username }}</span><button class="text-button" :disabled="loading" @click="logout">退出登录</button></template><button v-else class="text-button" :disabled="!auth.ready" @click="showAuth = !showAuth">登录 / 注册</button></div>
    </header>
    <main>
      <section class="intro">
        <p class="eyebrow">LESS NOISE, MORE SIGHT</p>
        <h1>把信息流，<br class="mobile-break" />变成阅读清单。</h1>
        <p class="intro-copy">订阅你关心的声音，收拢值得阅读的内容。</p>
      </section>
      <AuthPanel v-if="showAuth && !auth.user" @done="showAuth = false" @close="showAuth = false" />
      <nav v-if="auth.user" class="view-tabs" aria-label="工作台导航">
        <button v-for="tab in [{ id: 'reading', label: 'RSS 阅读' }, { id: 'agents', label: 'Agent 管理' }, { id: 'chats', label: '对话' }, { id: 'history', label: '阅读记录' }]" :key="tab.id" :class="{ active: view === tab.id }" :aria-current="view === tab.id ? 'page' : undefined" :disabled="loading" @click="view = tab.id">{{ tab.label }}</button>
      </nav>
      <AccountWorkspace v-if="auth.user && view !== 'reading'" :key="auth.user.id" :view="view" @open-digest="openDigest" @profiles-changed="loadAgents" />
      <div v-show="view === 'reading'" class="workspace">
        <aside class="panel settings">
          <div class="section-heading"><h2>本次阅读</h2><span class="step">01 / 配置</span></div>
          <form @submit.prevent="generate(false)">
            <fieldset :disabled="loading">
              <legend>选择信息源 <span>最多 5 个</span></legend>
              <label v-for="source in allSources" :key="source.url" class="source-option">
                <input v-model="selected" type="checkbox" :value="source.url" />
                <span>{{ source.name }}<small>{{ source.url.split('/')[2] }}</small></span>
              </label>
              <button v-if="!config" class="text-button" type="button" @click="loadConfig">重新连接后端</button>
              <label class="field-label" for="custom-urls">添加 RSS / Atom 地址</label>
              <textarea id="custom-urls" v-model="customUrls" rows="3" placeholder="https://example.com/feed&#10;每行一个地址" spellcheck="false"></textarea>
              <div class="control-row">
                <label for="limit">展示条数</label>
                <select id="limit" v-model.number="limit"><option :value="5">5 条</option><option :value="10">10 条</option><option :value="20">20 条</option></select>
              </div>
              <label class="field-label" for="mode">摘要方式</label>
              <select id="mode" v-model="mode" class="full-width">
                <option value="feed">订阅自带摘要</option>
                <option value="ai" :disabled="!aiEnabled">AI 中文摘要{{ aiEnabled ? '' : ' · 待配置' }}</option>
              </select>
              <label v-if="auth.user && profiles.length" class="field-label" for="reading-agent">阅读 Agent</label>
              <select v-if="auth.user && profiles.length" id="reading-agent" v-model="selectedAgent" class="full-width"><option v-for="profile in profiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></select>
              <p class="help">{{ aiEnabled ? `AI 摘要由 ${currentModel} 提供，基于订阅内容生成。` : '订阅摘要可直接使用；配置模型密钥后可启用 AI 中文摘要。' }}</p>
              <button class="primary" type="submit">{{ loading ? '正在采集与整理…' : '生成阅读清单' }}<span v-if="!loading" aria-hidden="true">↗</span></button>
              <button class="secondary" type="button" @click="generate(true)">查看示例</button>
            </fieldset>
          </form>
          <p class="session-note">{{ auth.user ? '生成结果自动保存到阅读记录。' : '登录后可保存订阅和阅读记录。' }}</p>
          <form v-if="auth.user" class="stacked-form source-form" @submit.prevent="saveSource">
            <h2>保存订阅</h2>
            <label>订阅名称<input v-model="sourceName" required maxlength="80" placeholder="例如：技术周刊" /></label>
            <label>订阅地址<input v-model="sourceUrl" type="url" required maxlength="2048" placeholder="https://example.com/feed" /></label>
            <button class="secondary" :disabled="savingSource || loading" type="submit">{{ savingSource ? '保存中…' : '保存订阅' }}</button>
            <div v-for="source in savedSources" :key="source.id" class="saved-source"><span>{{ source.name }}</span><button type="button" class="text-button danger" :disabled="loading" @click="removeSource(source)">删除</button></div>
          </form>
        </aside>
        <section class="reading-area" aria-label="阅读清单" :aria-busy="loading">
          <div v-if="error" class="notice error" role="alert">{{ error }}</div>
          <div v-if="loading" class="notice progress" role="status"><span class="spinner"></span>正在读取订阅内容{{ mode === 'ai' ? '并生成摘要' : '' }}，请稍候…</div>
          <template v-if="result">
            <div class="reading-header">
              <div><p class="eyebrow">YOUR READING LIST</p><h2>这一刻，值得关注</h2></div>
              <button class="export-button" type="button" @click="downloadDigest">导出 Markdown ↓</button>
            </div>
            <div class="summary-panel">
              <div class="summary-meta"><span class="badge">{{ result.demo ? '示例 · 非实时新闻' : result.mode === 'ai' ? 'AI 中文摘要' : '订阅摘要' }}</span><span>{{ result.articles.length }} 条内容</span></div>
              <p>{{ result.overview }}</p>
              <small>生成于 {{ formatTime(result.generated_at) }}{{ result.id ? ' · 已保存' : '' }}</small>
            </div>
            <div v-for="warning in result.warnings" :key="warning" class="notice" role="status">{{ warning }}</div>
            <div class="source-statuses" aria-label="信息源抓取结果">
              <span v-for="source in result.sources" :key="source.url" :class="{ failed: source.status === 'error' }">{{ source.status === 'ok' ? '✓' : '×' }} {{ source.name || source.url }} · {{ source.count }} 条</span>
            </div>
            <label class="search-label" for="search">在结果中查找<input id="search" v-model="search" type="search" placeholder="搜索标题、摘要或来源…" /></label>
            <div v-if="!visibleArticles.length" class="empty-result">{{ result.articles.length ? '没有匹配的内容，换个关键词试试。' : '信息源中暂无可展示的文章，可尝试更换订阅地址。' }}</div>
            <article v-for="(article, index) in visibleArticles" :key="article.id" class="article-card">
              <span class="article-number">{{ String(index + 1).padStart(2, '0') }}</span>
              <div class="article-content">
                <div class="article-meta"><span>{{ article.source }}</span><span>{{ article.summary_kind === 'ai' ? 'AI 摘要' : '订阅摘要' }}</span></div>
                <h3><a :href="article.url" target="_blank" rel="noopener noreferrer">{{ article.title }} <span aria-hidden="true">↗</span></a></h3>
                <p>{{ article.summary }}</p>
                <time :datetime="article.published_at || undefined">{{ formatTime(article.published_at) }}</time>
              </div>
            </article>
          </template>
          <div v-else-if="!loading" class="empty-state">
            <div class="radar" aria-hidden="true"><div></div><span></span><i></i></div>
            <p class="eyebrow">START WITH A SOURCE</p>
            <h2>你的下一条灵感，<br />从这里开始。</h2>
            <p>选择信息源，生成专属阅读清单。<br />也可以先查看示例，体验完整流程。</p>
            <button type="button" class="text-button" @click="generate(true)">探索示例清单 <span aria-hidden="true">→</span></button>
          </div>
        </section>
      </div>
    </main>
    <footer><span>SIGHT / 看见有价值的信息</span><span>RSS → 摘要 → 阅读</span></footer>
  </div>
</template>
