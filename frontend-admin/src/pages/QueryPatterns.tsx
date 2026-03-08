import React, { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, Tag, message, Popconfirm, Card, Typography } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;

interface QueryPattern {
    id: number;
    tier: string;
    pattern: string;
    description: string | null;
    is_active: boolean;
}

const QueryPatterns: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form] = Form.useForm();
    const queryClient = useQueryClient();

    const { data, isLoading } = useQuery({
        queryKey: ['query-patterns'],
        queryFn: async () => {
            const res = await api.get('/admin/query-patterns');
            return res.data;
        },
    });

    const createMutation = useMutation({
        mutationFn: (values: any) => api.post('/admin/query-patterns', values),
        onSuccess: () => {
            message.success('Pattern created');
            setIsModalVisible(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['query-patterns'] });
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data: d }: { id: number; data: any }) => api.put(`/admin/query-patterns/${id}`, d),
        onSuccess: () => {
            message.success('Pattern updated');
            setIsModalVisible(false);
            setEditingId(null);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['query-patterns'] });
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => api.delete(`/admin/query-patterns/${id}`),
        onSuccess: () => {
            message.success('Pattern deleted');
            queryClient.invalidateQueries({ queryKey: ['query-patterns'] });
        },
    });

    const handleAdd = () => {
        setEditingId(null);
        form.resetFields();
        form.setFieldsValue({ tier: 'simple', is_active: true });
        setIsModalVisible(true);
    };

    const handleEdit = (record: QueryPattern) => {
        setEditingId(record.id);
        form.setFieldsValue(record);
        setIsModalVisible(true);
    };

    const handleOk = () => {
        form.validateFields().then((values) => {
            if (editingId) {
                updateMutation.mutate({ id: editingId, data: values });
            } else {
                createMutation.mutate(values);
            }
        });
    };

    const columns: ColumnsType<QueryPattern> = [
        {
            title: 'Tier', dataIndex: 'tier', key: 'tier', width: 100,
            render: (t: string) => (
                <Tag color={t === 'simple' ? 'green' : t === 'complex' ? 'red' : 'blue'}>{t}</Tag>
            ),
            filters: [
                { text: 'Simple', value: 'simple' },
                { text: 'Complex', value: 'complex' },
            ],
            onFilter: (value, record) => record.tier === value,
        },
        {
            title: 'Pattern', dataIndex: 'pattern', key: 'pattern',
            render: (text: string) => <code style={{ fontSize: 12 }}>{text}</code>,
        },
        {
            title: 'Description', dataIndex: 'description', key: 'description', ellipsis: true,
            render: (t: string | null) => t || <Text type="secondary">-</Text>,
        },
        {
            title: 'Active', dataIndex: 'is_active', key: 'is_active', width: 80,
            render: (active: boolean) => <Tag color={active ? 'success' : 'default'}>{active ? 'Yes' : 'No'}</Tag>,
        },
        {
            title: 'Actions', key: 'actions', width: 100,
            render: (_, record) => (
                <Space>
                    <Button type="text" icon={<EditOutlined style={{ color: '#1890ff' }} />} onClick={() => handleEdit(record)} />
                    <Popconfirm title="Delete?" onConfirm={() => deleteMutation.mutate(record.id)} okText="Yes" cancelText="No">
                        <Button type="text" icon={<DeleteOutlined style={{ color: '#ff4d4f' }} />} />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2 style={{ margin: 0 }}>Query Complexity Patterns</h2>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>Add Pattern</Button>
            </div>

            <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                Patterns used to classify query complexity for model tier routing. Simple patterns use cheaper models, complex patterns use more capable models.
            </Text>

            <Card>
                <Table
                    dataSource={data?.patterns || []}
                    columns={columns}
                    rowKey="id"
                    loading={isLoading}
                    size="small"
                    pagination={{ pageSize: 20 }}
                />
            </Card>

            <Modal
                title={editingId ? 'Edit Pattern' : 'Add Pattern'}
                open={isModalVisible}
                onCancel={() => { setIsModalVisible(false); setEditingId(null); }}
                onOk={handleOk}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
                width={600}
            >
                <Form form={form} layout="vertical">
                    <Form.Item name="tier" label="Tier" rules={[{ required: true }]}>
                        <Select>
                            <Select.Option value="simple">Simple (cheap model)</Select.Option>
                            <Select.Option value="complex">Complex (capable model)</Select.Option>
                        </Select>
                    </Form.Item>
                    <Form.Item name="pattern" label="Pattern (regex)" rules={[{ required: true }]}>
                        <Input placeholder="e.g. ^(รวม|total|sum)" />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                        <Input placeholder="Brief description of what this pattern matches" />
                    </Form.Item>
                    <Form.Item name="is_active" label="Active" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default QueryPatterns;
