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
    Tooltip,
    Card,
    Tabs
} from 'antd';
import {
    EditOutlined,
    PlusOutlined,
    DeleteOutlined,
    StarFilled,
    EyeOutlined
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { providerService } from '../services/providerService';
import type { AIModel, AIProviderDetailed } from '../services/providerService';
import type { ColumnsType } from 'antd/es/table';

const { TextArea } = Input;

const Models: React.FC = () => {
    const [selectedProviderId, setSelectedProviderId] = useState<string>('');
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingModel, setEditingModel] = useState<AIModel | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [form] = Form.useForm();
    const queryClient = useQueryClient();

    // Fetch all providers
    const { data: providers } = useQuery({
        queryKey: ['providers'],
        queryFn: () => providerService.getAllProviders(true)
    });

    // Fetch models for selected provider
    const { data: models, isLoading } = useQuery({
        queryKey: ['models', selectedProviderId],
        queryFn: () => providerService.getModelsByProvider(selectedProviderId, true),
        enabled: !!selectedProviderId
    });

    const createMutation = useMutation({
        mutationFn: ({ providerId, data }: { providerId: string; data: any }) =>
            providerService.createModel(providerId, data),
        onSuccess: () => {
            message.success('Model created successfully');
            closeModal();
            queryClient.invalidateQueries({ queryKey: ['models', selectedProviderId] });
        },
        onError: (error: any) => {
            message.error(`Failed to create model: ${error.response?.data?.detail || error.message}`);
        }
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) =>
            providerService.updateModel(id, data),
        onSuccess: () => {
            message.success('Model updated successfully');
            closeModal();
            queryClient.invalidateQueries({ queryKey: ['models', selectedProviderId] });
        },
        onError: (error: any) => {
            message.error(`Failed to update model: ${error.response?.data?.detail || error.message}`);
        }
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => providerService.deleteModel(id),
        onSuccess: () => {
            message.success('Model deleted successfully');
            queryClient.invalidateQueries({ queryKey: ['models', selectedProviderId] });
        },
        onError: (error: any) => {
            message.error(`Failed to delete model: ${error.response?.data?.detail || error.message}`);
        }
    });

    // Auto-select first provider
    React.useEffect(() => {
        if (providers && providers.length > 0 && !selectedProviderId) {
            const activeProvider = providers.find(p => p.is_active) || providers[0];
            setSelectedProviderId(activeProvider.id);
        }
    }, [providers, selectedProviderId]);

    const handleCreate = () => {
        if (!selectedProviderId) {
            message.warning('Please select a provider first');
            return;
        }
        setEditingModel(null);
        setIsCreating(true);
        form.resetFields();
        form.setFieldsValue({
            is_active: true,
            is_default: false,
            supports_vision: false,
            priority: 50
        });
        setIsModalVisible(true);
    };

    const handleEdit = (record: AIModel) => {
        setEditingModel(record);
        setIsCreating(false);
        form.setFieldsValue(record);
        setIsModalVisible(true);
    };

    const closeModal = () => {
        setIsModalVisible(false);
        setEditingModel(null);
        setIsCreating(false);
        form.resetFields();
    };

    const handleOk = () => {
        form.validateFields().then(values => {
            if (isCreating) {
                createMutation.mutate({ providerId: selectedProviderId, data: values });
            } else if (editingModel) {
                updateMutation.mutate({ id: editingModel.id, data: values });
            }
        });
    };

    const handleDelete = (id: number) => {
        deleteMutation.mutate(id);
    };

    const columns: ColumnsType<AIModel> = [
        {
            title: 'Model ID',
            dataIndex: 'model_id',
            key: 'model_id',
            width: 200,
            render: (text, record) => (
                <Space>
                    <code>{text}</code>
                    {record.is_default && (
                        <Tooltip title="Default Model">
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
            width: 200
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
            title: 'Context Window',
            dataIndex: 'context_window',
            key: 'context_window',
            width: 130,
            render: (val) => val ? `${val.toLocaleString()}` : '-'
        },
        {
            title: 'Vision',
            dataIndex: 'supports_vision',
            key: 'supports_vision',
            width: 80,
            render: (val: boolean) => (
                val ? <Tag color="blue"><EyeOutlined /> Yes</Tag> : <Tag>No</Tag>
            )
        },
        {
            title: 'Cost/1M Tokens',
            dataIndex: 'cost_per_1m_tokens',
            key: 'cost_per_1m_tokens',
            width: 130,
            render: (val) => val ? `$${val.toFixed(2)}` : '-'
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
                        title="Delete model"
                        description="Are you sure you want to delete this model?"
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

    // Render tabs for each provider
    const tabItems = providers?.map(provider => ({
        key: provider.id,
        label: (
            <Space>
                <span>{provider.name}</span>
                {!provider.is_active && <Tag color="red">Inactive</Tag>}
            </Space>
        )
    }));

    return (
        <div style={{ padding: '24px' }}>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h2 style={{ margin: 0 }}>AI Models</h2>
                    <p style={{ color: '#666', margin: '4px 0 0 0' }}>
                        Manage AI models for each provider
                    </p>
                </div>
                <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={handleCreate}
                    disabled={!selectedProviderId}
                >
                    Add Model
                </Button>
            </div>

            <Card>
                <Tabs
                    activeKey={selectedProviderId}
                    onChange={setSelectedProviderId}
                    items={tabItems}
                />

                <Table
                    columns={columns}
                    dataSource={models}
                    loading={isLoading}
                    rowKey="id"
                    pagination={{ pageSize: 10, showSizeChanger: true }}
                    scroll={{ x: 1400 }}
                    style={{ marginTop: 16 }}
                />
            </Card>

            <Modal
                title={isCreating ? 'Create New Model' : 'Edit Model'}
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
                        label="Model ID"
                        name="model_id"
                        rules={[
                            { required: true, message: 'Please enter model ID' }
                        ]}
                        tooltip="Unique model identifier (e.g., claude-3-opus-20240229)"
                    >
                        <Input
                            placeholder="e.g., claude-3-opus-20240229"
                            disabled={!isCreating}
                        />
                    </Form.Item>

                    <Form.Item
                        label="Display Name"
                        name="display_name"
                        tooltip="User-friendly name shown in UI"
                    >
                        <Input placeholder="e.g., Claude 3 Opus" />
                    </Form.Item>

                    <Form.Item
                        label="Context Window"
                        name="context_window"
                        tooltip="Maximum number of tokens in context"
                    >
                        <Input type="number" placeholder="e.g., 200000" />
                    </Form.Item>

                    <Form.Item
                        label="Cost per 1M Tokens"
                        name="cost_per_1m_tokens"
                        tooltip="Cost in USD per 1 million tokens"
                    >
                        <Input type="number" step="0.01" placeholder="e.g., 15.00" />
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
                        <TextArea rows={3} placeholder="Brief description of this model" />
                    </Form.Item>

                    <Form.Item
                        label="Active"
                        name="is_active"
                        valuePropName="checked"
                        tooltip="Enable/disable this model"
                    >
                        <Switch />
                    </Form.Item>

                    <Form.Item
                        label="Set as Default"
                        name="is_default"
                        valuePropName="checked"
                        tooltip="Set this as the default model for this provider"
                    >
                        <Switch />
                    </Form.Item>

                    <Form.Item
                        label="Supports Vision"
                        name="supports_vision"
                        valuePropName="checked"
                        tooltip="Does this model support image inputs?"
                    >
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default Models;
