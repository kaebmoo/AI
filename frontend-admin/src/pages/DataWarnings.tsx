import React, { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, Tag, message, Popconfirm, Card } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import type { ColumnsType } from 'antd/es/table';

const { TextArea } = Input;

interface DataWarning {
    id: number;
    code: string;
    keywords: string;
    exclude_keywords: string | null;
    columns_to_check: string;
    message: string;
    severity: string;
    context_name: string | null;
    is_active: boolean;
}

const DataWarnings: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form] = Form.useForm();
    const queryClient = useQueryClient();

    const { data, isLoading } = useQuery({
        queryKey: ['data-warnings'],
        queryFn: async () => {
            const res = await api.get('/admin/warnings');
            return res.data;
        },
    });

    const createMutation = useMutation({
        mutationFn: (values: any) => api.post('/admin/warnings', values),
        onSuccess: () => {
            message.success('Warning created');
            setIsModalVisible(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['data-warnings'] });
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data: d }: { id: number; data: any }) => api.put(`/admin/warnings/${id}`, d),
        onSuccess: () => {
            message.success('Warning updated');
            setIsModalVisible(false);
            setEditingId(null);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['data-warnings'] });
        },
        onError: (err: any) => message.error(err.response?.data?.detail || 'Failed'),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => api.delete(`/admin/warnings/${id}`),
        onSuccess: () => {
            message.success('Warning deleted');
            queryClient.invalidateQueries({ queryKey: ['data-warnings'] });
        },
    });

    const handleAdd = () => {
        setEditingId(null);
        form.resetFields();
        form.setFieldsValue({ severity: 'warning', is_active: true });
        setIsModalVisible(true);
    };

    const handleEdit = (record: DataWarning) => {
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

    const columns: ColumnsType<DataWarning> = [
        { title: 'Code', dataIndex: 'code', key: 'code', width: 120 },
        {
            title: 'Message', dataIndex: 'message', key: 'message', ellipsis: true,
        },
        {
            title: 'Severity', dataIndex: 'severity', key: 'severity', width: 100,
            render: (s: string) => (
                <Tag color={s === 'important' ? 'red' : s === 'warning' ? 'orange' : 'blue'}>{s}</Tag>
            ),
        },
        {
            title: 'Context', dataIndex: 'context_name', key: 'context_name', width: 100,
            render: (c: string | null) => c ? <Tag>{c}</Tag> : <Tag color="default">all</Tag>,
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
                <h2 style={{ margin: 0 }}>Data Warnings</h2>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>Add Warning</Button>
            </div>

            <Card>
                <Table
                    dataSource={data?.warnings || []}
                    columns={columns}
                    rowKey="id"
                    loading={isLoading}
                    size="small"
                    pagination={{ pageSize: 10 }}
                />
            </Card>

            <Modal
                title={editingId ? 'Edit Warning' : 'Add Warning'}
                open={isModalVisible}
                onCancel={() => { setIsModalVisible(false); setEditingId(null); }}
                onOk={handleOk}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
                width={600}
            >
                <Form form={form} layout="vertical">
                    <Form.Item name="code" label="Code" rules={[{ required: true }]}>
                        <Input placeholder="e.g. WARN_REVENUE_OTHER" disabled={!!editingId} />
                    </Form.Item>
                    <Form.Item name="message" label="Warning Message" rules={[{ required: true }]}>
                        <TextArea rows={2} placeholder="Warning text shown to users" />
                    </Form.Item>
                    <Form.Item name="keywords" label="Keywords (JSON array)" rules={[{ required: true }]}>
                        <Input placeholder='["keyword1", "keyword2"]' />
                    </Form.Item>
                    <Form.Item name="exclude_keywords" label="Exclude Keywords (JSON array)">
                        <Input placeholder='["exclude1"]' />
                    </Form.Item>
                    <Form.Item name="columns_to_check" label="Columns to Check (JSON array)" rules={[{ required: true }]}>
                        <Input placeholder='["COLUMN_NAME"]' />
                    </Form.Item>
                    <Form.Item name="severity" label="Severity">
                        <Select>
                            <Select.Option value="info">Info</Select.Option>
                            <Select.Option value="warning">Warning</Select.Option>
                            <Select.Option value="important">Important</Select.Option>
                        </Select>
                    </Form.Item>
                    <Form.Item name="context_name" label="Context">
                        <Select allowClear placeholder="All contexts">
                            <Select.Option value="revenue">Revenue</Select.Option>
                            <Select.Option value="expense">Expense</Select.Option>
                            <Select.Option value="transfer_price">Transfer Price</Select.Option>
                        </Select>
                    </Form.Item>
                    <Form.Item name="is_active" label="Active" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default DataWarnings;
