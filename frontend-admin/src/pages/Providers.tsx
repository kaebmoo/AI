import React, { useState } from 'react';
import {
    Table,
    Button,
    Space,
    Modal,
    Form,
    Input,
    Select,
    Switch,
    Tag,
    message,
    Popconfirm,
    Tooltip
} from 'antd';
import {
    EditOutlined,
    PlusOutlined,
    DeleteOutlined,
    CheckCircleOutlined,
    StarOutlined,
    StarFilled
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { providerService } from '../services/providerService';
import type { AIProviderDetailed } from '../services/providerService';
import type { ColumnsType } from 'antd/es/table';

const { TextArea } = Input;

const Providers: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingProvider, setEditingProvider] = useState<AIProviderDetailed | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [form] = Form.useForm();
    const queryClient = useQueryClient();

    const { data: providers, isLoading } = useQuery({
        queryKey: ['providers'],
        queryFn: () => providerService.getAllProviders(true) // Include inactive
    });

    const createMutation = useMutation({
        mutationFn: (data: any) => providerService.createProvider(data),
        onSuccess: () => {
            message.success('Provider created successfully');
            closeModal();
            queryClient.invalidateQueries({ queryKey: ['providers'] });
        },
        onError: (error: any) => {
            message.error(`Failed to create provider: ${error.response?.data?.detail || error.message}`);
        }
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: any }) => providerService.updateProvider(id, data),
        onSuccess: () => {
            message.success('Provider updated successfully');
            closeModal();
            queryClient.invalidateQueries({ queryKey: ['providers'] });
        },
        onError: (error: any) => {
            message.error(`Failed to update provider: ${error.response?.data?.detail || error.message}`);
        }
    });

    const deleteMutation = useMutation({
        mutationFn: (id: string) => providerService.deleteProvider(id),
        onSuccess: () => {
            message.success('Provider deleted successfully');
            queryClient.invalidateQueries({ queryKey: ['providers'] });
        },
        onError: (error: any) => {
            message.error(`Failed to delete provider: ${error.response?.data?.detail || error.message}`);
        }
    });

    const handleCreate = () => {
        setEditingProvider(null);
        setIsCreating(true);
        form.resetFields();
        form.setFieldsValue({
            is_active: true,
            is_default: false,
            priority: 50
        });
        setIsModalVisible(true);
    };

    const handleEdit = (record: AIProviderDetailed) => {
        setEditingProvider(record);
        setIsCreating(false);
        form.setFieldsValue({
            ...record,
            provider_id: record.id // For display only in edit mode
        });
        setIsModalVisible(true);
    };

    const closeModal = () => {
        setIsModalVisible(false);
        setEditingProvider(null);
        setIsCreating(false);
        form.resetFields();
    };

    const handleOk = () => {
        form.validateFields().then(values => {
            if (isCreating) {
                createMutation.mutate(values);
            } else if (editingProvider) {
                updateMutation.mutate({ id: editingProvider.id, data: values });
            }
        });
    };

    const handleDelete = (id: string) => {
        deleteMutation.mutate(id);
    };

    const columns: ColumnsType<AIProviderDetailed> = [
        {
            title: 'Provider ID',
            dataIndex: 'id',
            key: 'id',
            width: 120,
            render: (text) => <code>{text}</code>
        },
        {
            title: 'Name',
            dataIndex: 'name',
            key: 'name',
            width: 150,
            render: (text, record) => (
                <Space>
                    <span>{text}</span>
                    {record.is_default && (
                        <Tooltip title="Default Provider">
                            <StarFilled style={{ color: '#faad14' }} />
                        </Tooltip>
                    )}
                </Space>
            )
        },
        {
            title: 'Display Name',
            dataIndex: 'display_name',
            key: 'display_name',
            width: 150
        },
        {
            title: 'Icon',
            dataIndex: 'icon',
            key: 'icon',
            width: 100
        },
        {
            title: 'Status',
            dataIndex: 'is_active',
            key: 'is_active',
            width: 100,
            render: (isActive: boolean) => (
                <Tag color={isActive ? 'green' : 'red'}>
                    {isActive ? 'Active' : 'Inactive'}
                </Tag>
            )
        },
        {
            title: 'Priority',
            dataIndex: 'priority',
            key: 'priority',
            width: 80,
            sorter: (a, b) => a.priority - b.priority
        },
        {
            title: 'Description',
            dataIndex: 'description',
            key: 'description',
            ellipsis: true
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 150,
            fixed: 'right',
            render: (_, record) => (
                <Space size="small">
                    <Button
                        type="link"
                        icon={<EditOutlined />}
                        onClick={() => handleEdit(record)}
                        size="small"
                    >
                        Edit
                    </Button>
                    <Popconfirm
                        title="Delete provider"
                        description="Are you sure you want to delete this provider? All associated models will also be deleted."
                        onConfirm={() => handleDelete(record.id)}
                        okText="Yes"
                        cancelText="No"
                        okButtonProps={{ danger: true }}
                    >
                        <Button
                            type="link"
                            danger
                            icon={<DeleteOutlined />}
                            size="small"
                        >
                            Delete
                        </Button>
                    </Popconfirm>
                </Space>
            )
        }
    ];

    return (
        <div style={{ padding: '24px' }}>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h2 style={{ margin: 0 }}>AI Providers</h2>
                    <p style={{ color: '#666', margin: '4px 0 0 0' }}>
                        Manage AI providers and their configurations
                    </p>
                </div>
                <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={handleCreate}
                >
                    Add Provider
                </Button>
            </div>

            <Table
                columns={columns}
                dataSource={providers}
                loading={isLoading}
                rowKey="id"
                pagination={{ pageSize: 10, showSizeChanger: true }}
                scroll={{ x: 1200 }}
            />

            <Modal
                title={isCreating ? 'Create New Provider' : 'Edit Provider'}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={closeModal}
                width={700}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
            >
                <Form
                    form={form}
                    layout="vertical"
                    style={{ marginTop: 16 }}
                >
                    <Form.Item
                        label="Provider ID"
                        name="provider_id"
                        rules={[
                            { required: isCreating, message: 'Please enter provider ID' },
                            { pattern: /^[a-z0-9_-]+$/, message: 'Only lowercase letters, numbers, hyphens, and underscores' }
                        ]}
                        tooltip="Unique identifier (e.g., claude, gemini, matcha)"
                    >
                        <Input
                            placeholder="e.g., claude, gemini, matcha"
                            disabled={!isCreating}
                        />
                    </Form.Item>

                    <Form.Item
                        label="Name"
                        name="name"
                        rules={[{ required: true, message: 'Please enter provider name' }]}
                    >
                        <Input placeholder="e.g., Claude" />
                    </Form.Item>

                    <Form.Item
                        label="Display Name"
                        name="display_name"
                        tooltip="User-friendly name shown in UI"
                    >
                        <Input placeholder="e.g., Claude (Anthropic)" />
                    </Form.Item>

                    <Form.Item
                        label="Icon"
                        name="icon"
                        tooltip="Ionicons icon name (e.g., bulb, sparkles, leaf)"
                    >
                        <Input placeholder="e.g., bulb, sparkles, leaf" />
                    </Form.Item>

                    <Form.Item
                        label="API Key Environment Variable"
                        name="api_key_env_var"
                        tooltip="Name of environment variable containing API key"
                    >
                        <Input placeholder="e.g., ANTHROPIC_API_KEY" />
                    </Form.Item>

                    <Form.Item
                        label="API URL Environment Variable"
                        name="api_url_env_var"
                        tooltip="Name of environment variable containing API URL (optional)"
                    >
                        <Input placeholder="e.g., ANTHROPIC_API_URL" />
                    </Form.Item>

                    <Form.Item
                        label="Default API URL"
                        name="default_api_url"
                        tooltip="Default API endpoint URL"
                    >
                        <Input placeholder="e.g., https://api.anthropic.com" />
                    </Form.Item>

                    <Form.Item
                        label="Priority"
                        name="priority"
                        tooltip="Display order (higher priority appears first)"
                    >
                        <Input type="number" placeholder="e.g., 50" />
                    </Form.Item>

                    <Form.Item
                        label="Description"
                        name="description"
                    >
                        <TextArea rows={3} placeholder="Brief description of this provider" />
                    </Form.Item>

                    <Form.Item
                        label="Active"
                        name="is_active"
                        valuePropName="checked"
                        tooltip="Enable/disable this provider"
                    >
                        <Switch />
                    </Form.Item>

                    <Form.Item
                        label="Set as Default"
                        name="is_default"
                        valuePropName="checked"
                        tooltip="Set this as the default provider for new users"
                    >
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default Providers;
