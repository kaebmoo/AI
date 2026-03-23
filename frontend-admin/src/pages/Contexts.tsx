import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Switch, message, Tag, Space, Card } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SyncOutlined } from '@ant-design/icons';
import type { SchemaContext } from '../types/schemaContext';
import { contextService } from '../services/contextService';
import { adminService } from '../services/adminService';

const Contexts: React.FC = () => {
    const [contexts, setContexts] = useState<SchemaContext[]>([]);
    const [loading, setLoading] = useState(false);
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [isEdit, setIsEdit] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form] = Form.useForm();
    const [submitting, setSubmitting] = useState(false);

    const fetchContexts = async () => {
        setLoading(true);
        try {
            const data = await contextService.getAll();
            setContexts(data.contexts);
        } catch (error) {
            message.error('Failed to load contexts');
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const handleSync = async () => {
        try {
            await adminService.refreshCache();
            message.success('Metadata cache refreshed successfully');
        } catch (error) {
            message.error('Failed to refresh cache');
        }
    };

    useEffect(() => {
        fetchContexts();
    }, []);

    const handleAdd = () => {
        setIsEdit(false);
        setEditingId(null);
        form.resetFields();
        form.setFieldsValue({
            is_active: true,
            priority: 0,
            keywords: '[]'
        });
        setIsModalVisible(true);
    };

    const handleEdit = (record: SchemaContext) => {
        setIsEdit(true);
        setEditingId(record.id);
        form.setFieldsValue({
            ...record,
            keywords: JSON.stringify(record.keywords || [], null, 2)
        });
        setIsModalVisible(true);
    };

    const handleDelete = async (id: number) => {
        try {
            await contextService.delete(id);
            message.success('Context deleted successfully');
            fetchContexts();
        } catch (error) {
            message.error('Failed to delete context');
        }
    };

    const handleOk = async () => {
        try {
            const values = await form.validateFields();
            setSubmitting(true);

            // Parse keywords JSON
            let keywords = [];
            try {
                keywords = JSON.parse(values.keywords);
                if (!Array.isArray(keywords)) throw new Error('Must be an array');
            } catch (e) {
                message.error('Keywords must be a valid JSON array of strings');
                setSubmitting(false);
                return;
            }

            const payload = {
                ...values,
                keywords
            };

            if (isEdit && editingId) {
                await contextService.update(editingId, payload);
                message.success('Context updated successfully');
            } else {
                await contextService.create(payload);
                message.success('Context created successfully');
            }

            setIsModalVisible(false);
            fetchContexts();
        } catch (error) {
            console.error(error);
            message.error('Operation failed');
        } finally {
            setSubmitting(false);
        }
    };

    const columns = [
        {
            title: 'ID',
            dataIndex: 'id',
            width: 60,
        },
        {
            title: 'Name',
            dataIndex: 'name',
            fontWeight: 'bold',
        },
        {
            title: 'Display',
            dataIndex: 'display_name',
        },
        {
            title: 'Main View',
            dataIndex: 'main_view',
            render: (text: string) => <Tag color="blue">{text}</Tag>
        },
        {
            title: 'Priority',
            dataIndex: 'priority',
            sorter: (a: SchemaContext, b: SchemaContext) => a.priority - b.priority,
            width: 100,
        },
        {
            title: 'Active',
            dataIndex: 'is_active',
            render: (active: boolean) => (
                <Tag color={active ? 'green' : 'red'}>
                    {active ? 'Active' : 'Inactive'}
                </Tag>
            ),
            width: 100,
        },
        {
            title: 'Keywords',
            dataIndex: 'keywords',
            render: (keywords: string[]) => (
                <Space wrap>
                    {keywords?.slice(0, 5).map(k => (
                        <Tag key={k}>{k}</Tag>
                    ))}
                    {keywords?.length > 5 && <Tag>+{keywords.length - 5}</Tag>}
                </Space>
            )
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 150,
            render: (_: any, record: SchemaContext) => (
                <Space>
                    <Button
                        icon={<EditOutlined />}
                        size="small"
                        onClick={() => handleEdit(record)}
                    />
                    <Button
                        icon={<DeleteOutlined />}
                        size="small"
                        danger
                        onClick={() => {
                            Modal.confirm({
                                title: 'Delete Context',
                                content: `Are you sure you want to delete context "${record.name}"?`,
                                onOk: () => handleDelete(record.id)
                            });
                        }}
                    />
                </Space>
            ),
        }
    ];

    return (
        <div style={{ padding: 24 }}>
            <Card
                title="Data Contexts Management"
                extra={
                    <Space>
                        <Button
                            icon={<SyncOutlined />}
                            onClick={handleSync}
                        >
                            Sync Metadata
                        </Button>
                        <Button
                            type="primary"
                            icon={<PlusOutlined />}
                            onClick={handleAdd}
                        >
                            Add Context
                        </Button>
                    </Space>
                }
            >
                <Table
                    columns={columns}
                    dataSource={contexts}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10 }}
                />
            </Card>

            <Modal
                title={isEdit ? "Edit Context" : "Add Context"}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={() => setIsModalVisible(false)}
                confirmLoading={submitting}
                width={700}
            >
                <Form
                    form={form}
                    layout="vertical"
                >
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                        <Form.Item
                            name="name"
                            label="Internal Name (e.g., 'revenue')"
                            rules={[{ required: true, message: 'Please enter internal name' }]}
                        >
                            <Input placeholder="revenue" disabled={isEdit} />
                        </Form.Item>
                        <Form.Item
                            name="display_name"
                            label="Display Name (e.g., 'รายได้')"
                            rules={[{ required: true }]}
                        >
                            <Input placeholder="รายได้" />
                        </Form.Item>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                        <Form.Item
                            name="main_view"
                            label="Main View/Table"
                            rules={[{ required: true }]}
                        >
                            <Input placeholder="revenue_search" />
                        </Form.Item>
                        <Form.Item
                            name="priority"
                            label="Routing Priority"
                        >
                            <InputNumber style={{ width: '100%' }} min={0} />
                        </Form.Item>
                    </div>

                    <Form.Item
                        name="instruction_th"
                        label="Prompt Instruction (TH)"
                        tooltip="Specific rules for Thai prompt (will be injected into system prompt)"
                    >
                        <Input.TextArea rows={4} placeholder="- Avoid using..." />
                    </Form.Item>

                    <Form.Item
                        name="instruction_en"
                        label="Prompt Instruction (EN)"
                        tooltip="Specific rules for English prompt"
                    >
                        <Input.TextArea rows={4} placeholder="- Avoid using..." />
                    </Form.Item>

                    <Form.Item
                        name="description"
                        label="Description"
                    >
                        <Input.TextArea rows={2} />
                    </Form.Item>

                    <Form.Item
                        name="keywords"
                        label="Routing Keywords (JSON Array)"
                        tooltip="List of keywords that route to this context"
                        rules={[{ required: true }]}
                    >
                        <Input.TextArea
                            rows={4}
                            placeholder='["keyword1", "keyword2"]'
                            style={{ fontFamily: 'monospace' }}
                        />
                    </Form.Item>

                    <Form.Item
                        name="is_active"
                        valuePropName="checked"
                        label="Active Status"
                    >
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default Contexts;
