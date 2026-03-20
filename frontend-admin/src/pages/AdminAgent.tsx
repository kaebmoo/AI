import React, { useState, useRef, useEffect } from 'react'
import {
  Card, Input, Button, List, Typography, Tag, Space, Spin,
  Drawer, message, Popconfirm, Divider, Empty
} from 'antd'
import {
  SendOutlined, RobotOutlined, UserOutlined,
  CheckOutlined, CloseOutlined, HistoryOutlined,
  ToolOutlined, ReloadOutlined
} from '@ant-design/icons'
import { adminAgentService } from '../services/adminAgentService'
import type {
  AdminChatResponse,
  ConversationSummary,
  Message as AgentMessage
} from '../services/adminAgentService'

const { Text, Paragraph } = Typography
const { TextArea } = Input

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  toolCalls?: any[]
  pendingConfirmation?: any
  timestamp: Date
}

const AdminAgent: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState<number | undefined>()
  const [showHistory, setShowHistory] = useState(false)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [pendingConfirmation, setPendingConfirmation] = useState<any>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(scrollToBottom, [messages])

  const handleSend = async () => {
    if (!inputValue.trim() || loading) return

    const userMessage: ChatMessage = {
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    }
    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setLoading(true)

    try {
      const response = await adminAgentService.chat(inputValue.trim(), conversationId)
      setConversationId(response.conversation_id)

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.response,
        toolCalls: response.tool_calls,
        pendingConfirmation: response.pending_confirmation,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, assistantMessage])

      if (response.pending_confirmation) {
        setPendingConfirmation(response.pending_confirmation)
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || 'Error communicating with agent')
    } finally {
      setLoading(false)
    }
  }

  const handleConfirm = async () => {
    if (!conversationId) return
    setLoading(true)

    try {
      const response = await adminAgentService.confirm(conversationId)
      setPendingConfirmation(null)

      const confirmMessage: ChatMessage = {
        role: 'assistant',
        content: response.response,
        toolCalls: response.tool_calls,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, confirmMessage])
      message.success('Action confirmed and executed')
    } catch (error: any) {
      message.error('Failed to confirm action')
    } finally {
      setLoading(false)
    }
  }

  const handleReject = async () => {
    if (!conversationId) return

    try {
      await adminAgentService.reject(conversationId)
      setPendingConfirmation(null)

      const rejectMessage: ChatMessage = {
        role: 'assistant',
        content: 'ยกเลิกการดำเนินการ',
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, rejectMessage])
    } catch {
      // Ignore
    }
  }

  const handleNewChat = () => {
    setMessages([])
    setConversationId(undefined)
    setPendingConfirmation(null)
  }

  const loadConversations = async () => {
    try {
      const data = await adminAgentService.listConversations()
      setConversations(data)
      setShowHistory(true)
    } catch {
      message.error('Failed to load conversations')
    }
  }

  const loadConversation = async (id: number) => {
    try {
      const detail = await adminAgentService.getConversation(id)
      setConversationId(id)
      setMessages(
        detail.messages.map(m => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          toolCalls: m.tool_result ? [{ tool_name: m.tool_name, result: JSON.parse(m.tool_result) }] : undefined,
          timestamp: new Date(m.created_at),
        }))
      )
      setShowHistory(false)
    } catch {
      message.error('Failed to load conversation')
    }
  }

  const renderToolCall = (tc: any) => {
    const data = tc.result?.data
    const isArray = Array.isArray(data)
    const isObj = data && typeof data === 'object' && !isArray

    return (
      <div key={tc.tool_name} style={{ marginTop: 8, padding: 10, background: '#f6f8fa', borderRadius: 6, fontSize: 12 }}>
        <Space>
          <ToolOutlined />
          <Tag color="blue">{tc.tool_name}</Tag>
          {tc.result?.success !== undefined && (
            <Tag color={tc.result.success ? 'green' : 'red'}>
              {tc.result.success ? 'Success' : 'Failed'}
            </Tag>
          )}
          {tc.result?.total !== undefined && (
            <Tag>{tc.result.total} items</Tag>
          )}
        </Space>
        {tc.result?.message && (
          <div style={{ marginTop: 4, color: '#666' }}>{tc.result.message}</div>
        )}
        {/* Render array data as a mini table */}
        {isArray && data.length > 0 && (() => {
          // Determine which columns to show and how to truncate long values
          const allKeys = Object.keys(data[0]).filter(k => k !== 'is_active')
          // For SQL-like fields, truncate display
          const sqlKeys = new Set(['sql', 'expected_sql', 'generated_sql', 'target_condition'])
          const truncate = (val: any, key: string) => {
            if (val === null || val === undefined) return '-'
            const s = String(val)
            if (sqlKeys.has(key) && s.length > 60) return s.slice(0, 60) + '...'
            if (s.length > 120) return s.slice(0, 120) + '...'
            return s
          }

          return (
            <div style={{ marginTop: 8, maxHeight: 400, overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                <thead>
                  <tr style={{ background: '#e8e8e8', position: 'sticky', top: 0, zIndex: 1 }}>
                    <th style={{ padding: '4px 6px', textAlign: 'left', borderBottom: '1px solid #ddd', color: '#999' }}>#</th>
                    {allKeys.map(k => (
                      <th key={k} style={{ padding: '4px 6px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.map((row: any, i: number) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                      <td style={{ padding: '3px 6px', color: '#999' }}>{i + 1}</td>
                      {allKeys.map(k => (
                        <td key={k} style={{ padding: '3px 6px', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                            title={row[k] !== null && row[k] !== undefined ? String(row[k]) : ''}>
                          {truncate(row[k], k)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })()}
        {/* Render single object data as key-value */}
        {isObj && !isArray && (
          <div style={{ marginTop: 6, paddingLeft: 8 }}>
            {Object.entries(data).map(([k, v]) => (
              <div key={k} style={{ color: '#555' }}>
                <Text code style={{ fontSize: 11 }}>{k}</Text>: {String(v)}
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div style={{ padding: 24, height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space>
          <RobotOutlined style={{ fontSize: 24 }} />
          <Text strong style={{ fontSize: 18 }}>Admin Agent</Text>
          {conversationId && <Tag>Conv #{conversationId}</Tag>}
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={handleNewChat}>New Chat</Button>
          <Button icon={<HistoryOutlined />} onClick={loadConversations}>History</Button>
        </Space>
      </div>

      {/* Messages */}
      <Card
        style={{ flex: 1, overflow: 'auto', marginBottom: 16 }}
        bodyStyle={{ padding: 16 }}
      >
        {messages.length === 0 ? (
          <Empty
            description={
              <div>
                <p>Admin Agent ช่วยจัดการ configuration ของระบบ</p>
                <p style={{ color: '#999', fontSize: 12 }}>
                  ตัวอย่าง: "ค้นหา mapping สำหรับ datacom", "เพิ่ม rule ใหม่", "ดู feedback ล่าสุด"
                </p>
              </div>
            }
          />
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 12,
              }}
            >
              <div
                style={{
                  maxWidth: '80%',
                  padding: '10px 14px',
                  borderRadius: 12,
                  background: msg.role === 'user' ? '#1677ff' : '#f0f0f0',
                  color: msg.role === 'user' ? '#fff' : '#000',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4, gap: 6 }}>
                  {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                  <Text style={{ fontSize: 11, color: msg.role === 'user' ? '#ccc' : '#999' }}>
                    {msg.timestamp.toLocaleTimeString('th-TH')}
                  </Text>
                </div>
                <Paragraph style={{ margin: 0, color: 'inherit', whiteSpace: 'pre-wrap' }}>
                  {msg.content}
                </Paragraph>
                {msg.toolCalls?.map(renderToolCall)}
              </div>
            </div>
          ))
        )}

        {/* Pending confirmation */}
        {pendingConfirmation && (
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <Card size="small" style={{ display: 'inline-block', background: '#fffbe6', border: '1px solid #ffe58f' }}>
              <Space>
                <Text>ยืนยันการดำเนินการ?</Text>
                <Button
                  type="primary"
                  icon={<CheckOutlined />}
                  onClick={handleConfirm}
                  loading={loading}
                  size="small"
                >
                  ยืนยัน
                </Button>
                <Button
                  icon={<CloseOutlined />}
                  onClick={handleReject}
                  size="small"
                >
                  ยกเลิก
                </Button>
              </Space>
            </Card>
          </div>
        )}

        {loading && (
          <div style={{ textAlign: 'center', padding: 16 }}>
            <Spin tip="Agent is thinking..." />
          </div>
        )}
        <div ref={messagesEndRef} />
      </Card>

      {/* Input */}
      <div style={{ display: 'flex', gap: 8 }}>
        <TextArea
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onPressEnter={e => {
            if (!e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder="พิมพ์คำสั่งหรือคำถาม... (Shift+Enter = new line)"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={loading}
          style={{ flex: 1 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          loading={loading}
          style={{ height: 'auto' }}
        >
          Send
        </Button>
      </div>

      {/* History Drawer */}
      <Drawer
        title="Conversation History"
        open={showHistory}
        onClose={() => setShowHistory(false)}
        width={400}
      >
        <List
          dataSource={conversations}
          renderItem={conv => (
            <List.Item
              style={{ cursor: 'pointer' }}
              onClick={() => loadConversation(conv.id)}
            >
              <List.Item.Meta
                title={conv.title}
                description={
                  <Space>
                    <Text type="secondary">{new Date(conv.updated_at).toLocaleDateString('th-TH')}</Text>
                    <Tag>{conv.message_count} messages</Tag>
                  </Space>
                }
              />
            </List.Item>
          )}
          locale={{ emptyText: 'No conversations yet' }}
        />
      </Drawer>
    </div>
  )
}

export default AdminAgent
