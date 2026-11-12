import { reactive } from 'vue'

export const auth = reactive({ user: null, csrfToken: '', ready: false })

export async function api(path, options = {}) {
  let response
  try {
    response = await fetch(path, {
      ...options,
      credentials: 'same-origin',
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(auth.csrfToken ? { 'X-CSRF-Token': auth.csrfToken } : {}),
        ...options.headers,
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: options.signal ?? AbortSignal.timeout(15000),
    })
  } catch (error) {
    throw new Error(error.name === 'TimeoutError' ? '请求超时，请稍后重试。' : '无法连接后端，请确认服务已启动。')
  }
  const data = response.status === 204 ? {} : await response.json()
  if (response.status === 401) auth.user = null
  if (!response.ok) throw new Error(data.message || '操作失败，请重试。')
  if ('csrf_token' in data) auth.csrfToken = data.csrf_token
  if ('user' in data) auth.user = data.user
  return data
}

export async function initAuth() {
  try {
    await api('/api/auth/me')
  } finally {
    auth.ready = true
  }
}
