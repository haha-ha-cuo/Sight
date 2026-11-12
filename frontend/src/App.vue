<script setup>
import { computed, onMounted, ref } from 'vue'

const config = ref(null)
const selected = ref([])
const customUrls = ref('')
const limit = ref(10)
const mode = ref('feed')
const loading = ref(false)
const error = ref('')
const result = ref(null)
const search = ref('')
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
    const response = await fetch('/api/rss/config', { signal: AbortSignal.timeout(8000) })
    if (!response.ok) throw new Error('配置读取失败')
    config.value = await response.json()
    selected.value = config.value.sources.slice(0, 1).map((source) => source.url)
  } catch {
    error.value = '无法连接后端，请确认 Flask 已在 5001 端口启动后重试。'
  }
}

async function generate(demo = false) {
  error.value = ''
  if (!demo && (!urls.value.length || urls.value.length > 5)) {
    error.value = '请选择或输入 1–5 个订阅地址。'
    return
  }
  loading.value = true
  try {
    const response = await fetch('/api/digests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls: demo ? [] : urls.value, limit: limit.value, mode: demo ? 'feed' : mode.value, demo }),
      signal: AbortSignal.timeout(180000),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.message || '生成失败，请重试。')
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

onMounted(loadConfig)
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="Sight 首页"><span class="brand-mark">S</span> Sight<span class="brand-note">资讯阅读台</span></a>
      <span class="prototype">RSS 原型 · 01</span>
    </header>
    <main>
      <section class="intro">
        <p class="eyebrow">LESS NOISE, MORE SIGHT</p>
        <h1>把信息流，<br class="mobile-break" />变成阅读清单。</h1>
        <p class="intro-copy">订阅你关心的声音，收拢值得阅读的内容。</p>
      </section>
      <div class="workspace">
        <aside class="panel settings">
          <div class="section-heading"><h2>本次阅读</h2><span class="step">01 / 配置</span></div>
          <form @submit.prevent="generate(false)">
            <fieldset :disabled="loading">
              <legend>选择信息源 <span>最多 5 个</span></legend>
              <label v-for="source in config?.sources ?? []" :key="source.url" class="source-option">
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
                <option value="ai" :disabled="!config?.ai_available">AI 中文摘要{{ config?.ai_available ? '' : ' · 待配置' }}</option>
              </select>
              <p class="help">{{ config?.ai_available ? `AI 摘要由 ${config.model} 提供，基于订阅内容生成。` : '订阅摘要可直接使用；配置模型密钥后可启用 AI 中文摘要。' }}</p>
              <button class="primary" type="submit">{{ loading ? '正在采集与整理…' : '生成阅读清单' }}<span v-if="!loading" aria-hidden="true">↗</span></button>
              <button class="secondary" type="button" @click="generate(true)">查看示例</button>
            </fieldset>
          </form>
          <p class="session-note">结果仅保留在当前页面，刷新后清空。</p>
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
              <small>生成于 {{ formatTime(result.generated_at) }}</small>
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
