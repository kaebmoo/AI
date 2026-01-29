import React, { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, Tag, message, Popconfirm } from 'antd';
import { EditOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSchemaColumns, updateSchemaColumn, createSchemaColumn, deleteSchemaColumn } from '../services/schema';
import type { SchemaMetadata } from '../services/schema';
import type { ColumnsType } from 'antd/es/table';

const { TextArea } = Input;

const Schema: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [form] = Form.useForm();
    const queryClient = useQueryClient();

    const { data, isLoading } = useQuery({
        queryKey: ['schema'],
        queryFn: () => getSchemaColumns()
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) => updateSchemaColumn(id, data),
        onSuccess: () => {
            message.success('Column metadata updated successfully');
            closeModal();
            queryClient.invalidateQueries({ queryKey: ['schema'] });
        },
        onError: (error: any) => {
            message.error(`Failed to update metadata: ${error.response?.data?.detail || error.message}`);
        }
    });

    const createMutation = useMutation({
        mutationFn: (data: any) => createSchemaColumn(data),
        onSuccess: () => {
            message.success('Column created successfully');
            closeModal();
            queryClient.invalidateQueries({ queryKey: ['schema'] });
        },
        onError: (error: any) => {
            message.error(`Failed to create column: ${error.response?.data?.detail || error.message}`);
        }
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => deleteSchemaColumn(id),
        onSuccess: () => {
            message.success('Column deleted successfully');
            queryClient.invalidateQueries({ queryKey: ['schema'] });
        },
        onError: (error: any) => {
            message.error(`Failed to delete column: ${error.response?.data?.detail || error.message}`);
        }
    });

    const handleEdit = (record: SchemaMetadata) => {
        setEditingId(record.id);
        setIsCreating(false);
        form.setFieldsValue(record);
        setIsModalVisible(true);
    };

    const handleCreate = () => {
        setEditingId(null);
        setIsCreating(true);
        form.resetFields();
        // Set defaults
        form.setFieldsValue({
            data_type: 'VARCHAR',
            is_summable: false,
            is_groupable: false
        });
        setIsModalVisible(true);
    };

    const closeModal = () => {
        setIsModalVisible(false);
        setEditingId(null);
        setIsCreating(false);
        form.resetFields();
    };

    const handleOk = () => {
        form.validateFields().then(values => {
            if (isCreating) {
                createMutation.mutate(values);
            } else if (editingId) {
                updateMutation.mutate({ id: editingId, data: values });
            }
        });
    };

    const handleDelete = (id: number) => {
        deleteMutation.mutate(id);
    };





    const columns: ColumnsType<SchemaMetadata> = [
        {
            title: 'Table',
            dataIndex: 'table_name',
            key: 'table_name',
            // sorter: (a, b) => a.table_name.localeCompare(b.table_name),
            filters: Array.from(new Set(data?.columns.map(c => c.table_name) || [])).map(t => ({ text: t, value: t })),
            onFilter: (value, record) => record.table_name === value,
            width: 150,
        },
        {
            title: 'Column',
            dataIndex: 'column_name',
            key: 'column_name',
            width: 150,
        },
        {
            title: 'Type',
            dataIndex: 'data_type',
            key: 'data_type',
            width: 100,
            render: (text) => <Tag>{text}</Tag>
        },
        {
            title: 'Display Name (TH)',
            dataIndex: 'display_name_th',
            key: 'display_name_th',
        },
        {
            title: 'Display Name (EN)',
            dataIndex: 'display_name_en',
            key: 'display_name_en',
        },
        {
            title: 'Flags',
            key: 'flags',
            width: 150,
            render: (_, record) => (
                <Space>
                    {record.is_groupable && <Tag color="blue">GROUP</Tag>}
                    {record.is_summable && <Tag color="green">SUM</Tag>}
                </Space>
            )
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 80,
            render: (_, record) => (
                <Space>
                    <Button
                        type="text"
                        icon={<EditOutlined style={{ color: '#1890ff' }} />}
                        onClick={() => handleEdit(record)}
                    />
                    <Popconfirm
                        title="Delete this column?"
                        description="This action cannot be undone."
                        onConfirm={() => handleDelete(record.id)}
                        okText="Delete"
                        cancelText="Cancel"
                    >
                        <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                        />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h2 style={{ margin: 0 }}>Schema Explorer</h2>
                    <p style={{ color: '#888', margin: 0 }}>Manage database column metadata for AI context.</p>
                </div>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                    Add Column
                </Button>
            </div>

            <Table
                columns={columns}
                dataSource={data?.columns}
                rowKey="id"
                loading={isLoading}
                scroll={{ x: 1000 }}
                pagination={{ pageSize: 20 }}
            />

            <Modal
                title={isCreating ? "Add New Column" : "Edit Column Metadata"}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={closeModal}
                okText={isCreating ? "Create" : "Update"}
                confirmLoading={updateMutation.isPending || createMutation.isPending}
                width={700}
            >
                <Form
                    form={form}
                    layout="vertical"
                >
                    <div style={{ display: 'flex', gap: 16, marginBottom: 16, background: '#f5f5f5', padding: 12, borderRadius: 8 }}>
                        {isCreating ? (
                            <>
                                <Form.Item
                                    name="table_name"
                                    label="Table Name"
                                    style={{ flex: 1, marginBottom: 0 }}
                                    rules={[{ required: true }]}
                                >
                                    <Input placeholder="e.g. users" />
                                </Form.Item>
                                <Form.Item
                                    name="column_name"
                                    label="Column Name"
                                    style={{ flex: 1, marginBottom: 0 }}
                                    rules={[{ required: true }]}
                                >
                                    <Input placeholder="e.g. email" />
                                </Form.Item>
                                <Form.Item
                                    name="data_type"
                                    label="Data Type"
                                    style={{ width: 120, marginBottom: 0 }}
                                    rules={[{ required: true }]}
                                >
                                    <Select>
                                        <Select.Option value="VARCHAR">VARCHAR</Select.Option>
                                        <Select.Option value="INTEGER">INTEGER</Select.Option>
                                        <Select.Option value="FLOAT">FLOAT</Select.Option>
                                        <Select.Option value="BOOLEAN">BOOLEAN</Select.Option>
                                        <Select.Option value="DATE">DATE</Select.Option>
                                        <Select.Option value="TIMESTAMP">TIMESTAMP</Select.Option>
                                        <Select.Option value="TEXT">TEXT</Select.Option>
                                    </Select>
                                </Form.Item>
                            </>
                        ) : (
                            <>
                                <div style={{ flex: 1 }}><strong>Table:</strong> {form.getFieldValue('table_name')}</div>
                                <div style={{ flex: 1 }}><strong>Column:</strong> {form.getFieldValue('column_name')}</div>
                                <div style={{ width: 100 }}><strong>Type:</strong> {form.getFieldValue('data_type')}</div>
                            </>
                        )}
                    </div>

                    <Form.Item label="Display Names" style={{ marginBottom: 0 }}>
                        <Form.Item
                            name="display_name_th"
                            style={{ display: 'inline-block', width: 'calc(50% - 8px)' }}
                            label="Thai"
                        >
                            <Input placeholder="ชื่อภาษาไทย" />
                        </Form.Item>
                        <Form.Item
                            name="display_name_en"
                            style={{ display: 'inline-block', width: 'calc(50% - 8px)', margin: '0 0 0 16px' }}
                            label="English"
                        >
                            <Input placeholder="English Name" />
                        </Form.Item>
                    </Form.Item>

                    <Form.Item
                        name="description"
                        label="Description"
                    >
                        <TextArea rows={2} placeholder="Description for AI understanding" />
                    </Form.Item>

                    <Form.Item
                        name="special_notes"
                        label="Special Notes"
                    >
                        <TextArea rows={2} placeholder="Any specific logic or caveats" />
                    </Form.Item>

                    <Space size="large">
                        <Form.Item
                            name="is_groupable"
                            label="Groupable"
                            valuePropName="checked"
                        >
                            <Switch />
                        </Form.Item>
                        <Form.Item
                            name="is_summable"
                            label="Summable (Metric)"
                            valuePropName="checked"
                        >
                            <Switch />
                        </Form.Item>
                    </Space>
                </Form>
            </Modal>
        </div>
    );
};

export default Schema;
