import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber,
  Tag, Space, Typography, message, Popconfirm, Alert, Statistic, Row, Col
} from 'antd'
import {
  PlusOutlined, KeyOutlined, DeleteOutlined,
  CopyOutlined, BarChartOutlined
} from '@ant-design/icons'
import { apiKeyService } from '../services/apiKeyService'
import type { APIKey, APIKeyWithRawKey, UsageStats } from '../services/apiKeyService'

const { Text } = Typography

const ApiKeys: React.FC = () => {
  const [keys, setKeys] = useState<APIKey[]>([])
  const [loading, setLoading] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [newKeyResult, setNewKeyResult] = useState<APIKeyWithRawKey | null>(null)
  const [usageModal, setUsageModal] = useState<{ keyId: number; name: string } | null>(null)
  const [usageStats, setUsageStats] = useState<UsageStats | null>(null)
  const [form] = Form.useForm()

  const loadKeys = async () => {
    setLoading(true)
    try {
      const data = await apiKeyService.list()
      setKeys(data)
    } catch {
      message.error('Failed to load API keys')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadKeys() }, [])

  const handleCreate = async (values: any) => {
    try {
      const result = await apiKeyService.create(
        values.name,
        values.scopes,
        values.rate_limit_per_minute,
        values.rate_limit_per_day,
      )
      setNewKeyResult(result)
      setCreateModalOpen(false)
      form.resetFields()
      loadKeys()
      message.success('API key created')
    } catch {
      message.error('Failed to create API key')
    }
  }

  const handleRevoke = async (keyId: number) => {
    try {
      await apiKeyService.revoke(keyId)
      loadKeys()
      message.success('API key revoked')
    } catch {
      message.error('Failed to revoke')
    }
  }

  const handleViewUsage = async (keyId: number, name: string) => {
    setUsageModal({ keyId, name })
    try {
      const stats = await apiKeyService.getUsage(keyId)
      setUsageStats(stats)
    } catch {
      message.error('Failed to load usage')
    }
  }

  const columns = [
    {
      title: 'Key Prefix',
      dataIndex: 'key_prefix',
      render: (v: string) => <Text code>{v}...</Text>,
    },
    { title: 'Name', dataIndex: 'name' },
    {
      title: 'Scopes',
      dataIndex: 'scopes',
      render: (v: string) => v.split(',').map(s => <Tag key={s} color="blue">{s.trim()}</Tag>),
    },
    {
      title: 'Rate Limit',
      render: (_: any, r: APIKey) => `${r.rate_limit_per_minute}/min, ${r.rate_limit_per_day}/day`,
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? 'Active' : 'Revoked'}</Tag>,
    },
    {
      title: 'Last Used',
      dataIndex: 'last_used_at',
      render: (v: string | null) => v && v !== 'None' ? new Date(v).toLocaleDateString('th-TH') : '-',
    },
    {
      title: 'Actions',
      render: (_: any, r: APIKey) => (
        <Space>
          <Button
            size="small"
            icon={<BarChartOutlined />}
            onClick={() => handleViewUsage(r.id, r.name)}
          >
            Usage
          </Button>
          {r.is_active && (
            <Popconfirm title="Revoke this key?" onConfirm={() => handleRevoke(r.id)}>
              <Button size="small" danger icon={<DeleteOutlined />}>Revoke</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space>
          <KeyOutlined style={{ fontSize: 24 }} />
          <Text strong style={{ fontSize: 18 }}>API Keys</Text>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
          Create API Key
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={keys}
        rowKey="id"
        loading={loading}
        pagination={false}
      />

      {/* Create Modal */}
      <Modal
        title="Create New API Key"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} onFinish={handleCreate} layout="vertical"
          initialValues={{ scopes: 'query', rate_limit_per_minute: 30, rate_limit_per_day: 1000 }}
        >
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="e.g., OpenMiniCrew Bot" />
          </Form.Item>
          <Form.Item name="scopes" label="Scopes">
            <Select>
              <Select.Option value="query">query (read-only)</Select.Option>
              <Select.Option value="query,admin">query + admin</Select.Option>
              <Select.Option value="full">full (all access)</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="rate_limit_per_minute" label="Rate Limit (per minute)">
            <InputNumber min={1} max={1000} />
          </Form.Item>
          <Form.Item name="rate_limit_per_day" label="Rate Limit (per day)">
            <InputNumber min={1} max={100000} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Raw Key Display Modal */}
      <Modal
        title="API Key Created"
        open={!!newKeyResult}
        onCancel={() => setNewKeyResult(null)}
        onOk={() => setNewKeyResult(null)}
        footer={<Button type="primary" onClick={() => setNewKeyResult(null)}>I've saved the key</Button>}
      >
        <Alert
          type="warning"
          message="Save this key now! It will not be shown again."
          style={{ marginBottom: 16 }}
        />
        <div style={{ background: '#f5f5f5', padding: 16, borderRadius: 8, fontFamily: 'monospace', wordBreak: 'break-all' }}>
          {newKeyResult?.raw_key}
        </div>
        <Button
          icon={<CopyOutlined />}
          style={{ marginTop: 8 }}
          onClick={() => {
            navigator.clipboard.writeText(newKeyResult?.raw_key || '')
            message.success('Copied!')
          }}
        >
          Copy to clipboard
        </Button>
      </Modal>

      {/* Usage Modal */}
      <Modal
        title={`Usage — ${usageModal?.name}`}
        open={!!usageModal}
        onCancel={() => { setUsageModal(null); setUsageStats(null) }}
        footer={null}
        width={600}
      >
        {usageStats && (
          <>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Statistic title="Total Requests" value={usageStats.total_requests} />
              </Col>
              <Col span={12}>
                <Statistic title="Total Tokens" value={usageStats.total_tokens} />
              </Col>
            </Row>
            <Table
              size="small"
              columns={[
                { title: 'Date', dataIndex: 'date' },
                { title: 'Requests', dataIndex: 'requests' },
                { title: 'Tokens', dataIndex: 'tokens' },
              ]}
              dataSource={usageStats.daily}
              rowKey="date"
              pagination={false}
            />
          </>
        )}
      </Modal>
    </div>
  )
}

export default ApiKeys
