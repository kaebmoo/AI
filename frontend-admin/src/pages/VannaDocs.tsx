import React, { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, Tag, message, Popconfirm, Alert } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SyncOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getVannaDocs, createVannaDoc, updateVannaDoc, deleteVannaDoc, getBrainSyncStatus } from '../services/vannaDocs';
import { adminService } from '../services/adminService';
import type { VannaDoc } from '../services/vannaDocs';
import type { ColumnsType } from 'antd/es/table';

const { Option } = Select;
const { TextArea } = Input;

const VannaDocs: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [searchText, setSearchText] = useState('');
    const [form] = Form.useForm();
    const queryClient = useQueryClient();

    const { data, isLoading } = useQuery({
        queryKey: ['vanna-docs'],
        queryFn: () => getVannaDocs(),
    });

    const { data: syncStatus } = useQuery({
        queryKey: ['brain-sync-status'],
        queryFn: getBrainSyncStatus,
    });

    const createMutation = useMutation({
        mutationFn: createVannaDoc,
        onSuccess: () => {
            message.success('Document created successfully');
            setIsModalVisible(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['vanna-docs'] });
            queryClient.invalidateQueries({ queryKey: ['brain-sync-status'] });
        },
        onError: (error: any) => {
            message.error(`Failed to create: ${error.response?.data?.detail || error.message}`);
        },
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) => updateVannaDoc(id, data),
        onSuccess: () => {
            message.success('Document updated successfully');
            setIsModalVisible(false);
            setEditingId(null);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['vanna-docs'] });
            queryClient.invalidateQueries({ queryKey: ['brain-sync-status'] });
        },
        onError: (error: any) => {
            message.error(`Failed to update: ${error.response?.data?.detail || error.message}`);
        },
    });

    const deleteMutation = useMutation({
        mutationFn: deleteVannaDoc,
        onSuccess: () => {
            message.success('Document deleted');
            queryClient.invalidateQueries({ queryKey: ['vanna-docs'] });
            queryClient.invalidateQueries({ queryKey: ['brain-sync-status'] });
        },
    });

    const syncBrainMutation = useMutation({
        mutationFn: adminService.syncBrain,
        onSuccess: () => {
            message.success('Vanna Brain sync completed');
            queryClient.invalidateQueries({ queryKey: ['brain-sync-status'] });
        },
        onError: (error: any) => {
            message.error(`Failed to sync brain: ${error.response?.data?.detail || error.message}`);
        },
    });

    const handleAdd = () => {
        setEditingId(null);
        form.resetFields();
        form.setFieldsValue({ is_active: true, category: 'guide' });
        setIsModalVisible(true);
    };

    const handleEdit = (record: VannaDoc) => {
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

    const categoryColors: Record<string, string> = {
        guide: 'blue',
        best_practice: 'green',
        workflow: 'orange',
    };

    const columns: ColumnsType<VannaDoc> = [
        {
            title: 'Key',
            dataIndex: 'doc_key',
            key: 'doc_key',
            width: 200,
            render: (text: string) => <code>{text}</code>,
        },
        {
            title: 'Title',
            dataIndex: 'title',
            key: 'title',
            ellipsis: true,
        },
        {
            title: 'Category',
            dataIndex: 'category',
            key: 'category',
            width: 130,
            render: (cat: string) => (
                <Tag color={categoryColors[cat] || 'default'}>{cat}</Tag>
            ),
        },
        {
            title: 'Context',
            dataIndex: 'context_name',
            key: 'context_name',
            width: 120,
            render: (ctx: string | null) =>
                ctx ? <Tag>{ctx}</Tag> : <span style={{ color: '#999' }}>All</span>,
        },
        {
            title: 'Active',
            dataIndex: 'is_active',
            key: 'is_active',
            width: 80,
            render: (active: boolean) =>
                active ? <Tag color="green">Yes</Tag> : <Tag color="red">No</Tag>,
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 100,
            render: (_, record) => (
                <Space>
                    <Button
                        type="text"
                        icon={<EditOutlined style={{ color: '#1890ff' }} />}
                        onClick={() => handleEdit(record)}
                    />
                    <Popconfirm
                        title="Delete this document?"
                        onConfirm={() => deleteMutation.mutate(record.id)}
                        okText="Yes"
                        cancelText="No"
                    >
                        <Button
                            type="text"
                            icon={<DeleteOutlined style={{ color: '#ff4d4f' }} />}
                        />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div>
            {syncStatus?.needs_sync && (
                <Alert
                    message="Brain Sync Required"
                    description="Knowledge has been updated since last Brain Sync. You can sync from this page or from Settings."
                    type="warning"
                    showIcon
                    icon={<SyncOutlined spin />}
                    action={
                        <Button
                            type="primary"
                            icon={<SyncOutlined />}
                            loading={syncBrainMutation.isPending}
                            onClick={() => syncBrainMutation.mutate()}
                        >
                            Sync Brain
                        </Button>
                    }
                    style={{ marginBottom: 16 }}
                />
            )}

            <div
                style={{
                    marginBottom: 16,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                }}
            >
                <h2 style={{ margin: 0 }}>Vanna Knowledge</h2>
                <Space>
                    <Button
                        icon={<SyncOutlined />}
                        onClick={() => syncBrainMutation.mutate()}
                        loading={syncBrainMutation.isPending}
                    >
                        Sync Brain
                    </Button>
                    <Input.Search
                        placeholder="Search docs..."
                        allowClear
                        onSearch={(value) => setSearchText(value)}
                        onChange={(e) => setSearchText(e.target.value)}
                        style={{ width: 300 }}
                    />
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                        Add Document
                    </Button>
                </Space>
            </div>

            <Table
                columns={columns}
                dataSource={data?.docs.filter((doc: VannaDoc) => {
                    if (!searchText) return true;
                    const s = searchText.toLowerCase();
                    return (
                        doc.doc_key.toLowerCase().includes(s) ||
                        doc.title.toLowerCase().includes(s) ||
                        doc.content.toLowerCase().includes(s) ||
                        (doc.context_name && doc.context_name.toLowerCase().includes(s))
                    );
                })}
                rowKey="id"
                loading={isLoading}
                expandable={{
                    expandedRowRender: (record) => (
                        <pre
                            style={{
                                whiteSpace: 'pre-wrap',
                                background: '#fafafa',
                                padding: 12,
                                borderRadius: 4,
                                maxHeight: 400,
                                overflow: 'auto',
                            }}
                        >
                            {record.content}
                        </pre>
                    ),
                    rowExpandable: () => true,
                }}
            />

            <Modal
                title={editingId ? 'Edit Document' : 'Create New Document'}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={() => setIsModalVisible(false)}
                okText={editingId ? 'Update' : 'Create'}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
                width={700}
            >
                <Form form={form} layout="vertical">
                    <Form.Item
                        name="doc_key"
                        label="Document Key (unique)"
                        rules={[{ required: true, message: 'Please enter a unique key' }]}
                    >
                        <Input placeholder="e.g. hierarchy_concept" disabled={!!editingId} />
                    </Form.Item>

                    <Form.Item
                        name="title"
                        label="Title"
                        rules={[{ required: true, message: 'Please enter title' }]}
                    >
                        <Input placeholder="e.g. Hierarchy Levels and Cross-Level OR Danger" />
                    </Form.Item>

                    <Form.Item
                        name="content"
                        label="Content"
                        rules={[{ required: true, message: 'Please enter content' }]}
                    >
                        <TextArea
                            rows={10}
                            placeholder="Knowledge content for Vanna RAG training..."
                            style={{ fontFamily: 'monospace' }}
                        />
                    </Form.Item>

                    <Form.Item label="Categorization" style={{ marginBottom: 0 }}>
                        <Form.Item
                            name="category"
                            style={{ display: 'inline-block', width: 'calc(50% - 8px)' }}
                        >
                            <Select>
                                <Option value="guide">Guide</Option>
                                <Option value="best_practice">Best Practice</Option>
                                <Option value="workflow">Workflow</Option>
                            </Select>
                        </Form.Item>
                        <Form.Item
                            name="context_name"
                            style={{
                                display: 'inline-block',
                                width: 'calc(50% - 8px)',
                                margin: '0 0 0 16px',
                            }}
                        >
                            <Input placeholder="Context name (blank = all)" />
                        </Form.Item>
                    </Form.Item>

                    <Form.Item name="is_active" label="Active" valuePropName="checked">
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default VannaDocs;
