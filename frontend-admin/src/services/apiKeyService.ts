import api from './api'

export interface APIKey {
  id: number
  key_prefix: string
  name: string
  user_id: number
  scopes: string
  rate_limit_per_minute: number
  rate_limit_per_day: number
  is_active: boolean
  last_used_at: string | null
  created_at: string | null
}

export interface APIKeyWithRawKey extends APIKey {
  raw_key: string
}

export interface UsageStats {
  total_requests: number
  total_tokens: number
  daily: { date: string; requests: number; tokens: number }[]
}

export const apiKeyService = {
  async create(name: string, scopes = 'query', rateLimitPerMinute = 30, rateLimitPerDay = 1000): Promise<APIKeyWithRawKey> {
    const { data } = await api.post('/admin/api-keys', {
      name,
      scopes,
      rate_limit_per_minute: rateLimitPerMinute,
      rate_limit_per_day: rateLimitPerDay,
    })
    return data
  },

  async list(): Promise<APIKey[]> {
    const { data } = await api.get('/admin/api-keys')
    return data
  },

  async revoke(keyId: number): Promise<void> {
    await api.delete(`/admin/api-keys/${keyId}`)
  },

  async getUsage(keyId: number, days = 30): Promise<UsageStats> {
    const { data } = await api.get(`/admin/api-keys/${keyId}/usage`, { params: { days } })
    return data
  },
}
