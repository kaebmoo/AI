import api from './api'

export interface ToolCallInfo {
  tool_name: string
  tool_args: Record<string, any>
  result?: Record<string, any>
}

export interface PendingConfirmation {
  tool_name: string
  tool_args: Record<string, any>
  description: string
  message: string
}

export interface AdminChatResponse {
  response: string
  tool_calls: ToolCallInfo[]
  pending_confirmation: PendingConfirmation | null
  conversation_id: number
}

export interface ConversationSummary {
  id: number
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface Message {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  tool_name?: string
  tool_args?: string
  tool_result?: string
  created_at: string
}

export interface ConversationDetail {
  id: number
  title: string
  created_at: string
  messages: Message[]
}

export const adminAgentService = {
  async chat(message: string, conversationId?: number): Promise<AdminChatResponse> {
    const { data } = await api.post('/admin/agent/chat', {
      message,
      conversation_id: conversationId,
    })
    return data
  },

  async confirm(conversationId: number): Promise<AdminChatResponse> {
    const { data } = await api.post(`/admin/agent/chat/${conversationId}/confirm`, {
      confirmed: true,
    })
    return data
  },

  async reject(conversationId: number): Promise<AdminChatResponse> {
    const { data } = await api.post(`/admin/agent/chat/${conversationId}/confirm`, {
      confirmed: false,
    })
    return data
  },

  async listConversations(limit = 20): Promise<ConversationSummary[]> {
    const { data } = await api.get('/admin/agent/conversations', { params: { limit } })
    return data
  },

  async getConversation(conversationId: number): Promise<ConversationDetail> {
    const { data } = await api.get(`/admin/agent/conversations/${conversationId}`)
    return data
  },
}
